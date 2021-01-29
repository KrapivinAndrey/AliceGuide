import csv
import enum
import inspect
import random
import sys

from guide import intents, state
from guide.alice import Request
from guide.responce_helpers import button, image_gallery
from guide.scenes_util import Scene


class QuestionType(enum.Enum):
    unknown = 1
    simple = 2
    hard = 3
    attention = 4

    @classmethod
    def from_request(cls, request: Request, intent_name: str):
        slot = request.intents[intent_name]["slots"]["question_type"]["value"]
        if slot == "simple":
            return cls.simple
        elif slot == "hard":
            return cls.hard
        elif slot == "attention":
            return cls.attention
        else:
            return cls.unknown

    @classmethod
    def from_state(cls, request: Request):
        slot = request.state_session[state.QUESTION_TYPE]
        if slot == "simple":
            return cls.simple
        elif slot == "hard":
            return cls.hard
        elif slot == "attention":
            return cls.attention
        else:
            return cls.unknown

    def russian(self):
        return {
            self.simple: "простой",
            self.hard: "сложный",
            self.attention: "на внимательность",
            self.unknown: "неизвестный",
        }[self]


class GlobalScene(Scene):
    def reply(self, request: Request):
        pass

    def handle_global_intents(self, request):
        if intents.TELL_ABOUT in request.intents:
            return WhoIs()

    def handle_local_intents(self, request: Request):
        pass


class Welcome(GlobalScene):
    def reply(self, request: Request):
        text = (
            "Я могу провести экскурсию по памятнику "
            "могу рассказать, про каждую фигуру на памятнике "
            "а можем сыграть в викторину"
        )
        return self.make_response(
            request,
            text,
            buttons=[
                button("Сыграть в викторину"),
                button("Расскажи экскурсию"),
            ],
        )

    def handle_local_intents(self, request: Request):
        if intents.START_TOUR in request.intents:
            return StartTour()
        elif intents.START_GAME in request.intents:
            return StartGame()


class StartTour(GlobalScene):
    def reply(self, request: Request):
        text = "Наша экскурсия начинается с ..."  # TODO сценарий "Экскурсия"
        return self.make_response(request, text)

    def handle_local_intents(self, request: Request):
        pass


class StartGame(GlobalScene):
    def reply(self, request: Request):
        text = (
            "Вопросы бывают простые, сложные и на внимательность.\n"
            "В простых вопросах будут варианты ответа.\n"
            "В сложных подсказок не будет.\n"
            'А чтобы правильно ответить на вопрос "На внимательность" хорошо бы видеть сам памятник '
            "или его фотографии.\n"
            "Начнем с простого вопроса?"
        )
        return self.make_response(
            request,
            text,
            buttons=[
                button("Простой"),
                button("Сложный"),
                button("На внимательность"),
            ],
            state={state.QUESTION_TYPE: "simple"},
        )

    def handle_local_intents(self, request: Request):
        question_type = QuestionType.unknown
        if intents.GAME_QUESTION in request.intents:
            question_type = QuestionType.from_request(request, intents.GAME_QUESTION)
        elif intents.CONFIRM in request.intents:
            question_type = QuestionType.from_state(request)
        if question_type != QuestionType.unknown:
            return QuestionScene()


class QuestionScene(GlobalScene):
    @staticmethod
    def get_questions(type: QuestionType):
        with open("guide/questions.csv", mode="r", encoding="utf-8") as in_file:
            reader = csv.DictReader(in_file, delimiter=",")
            return [r for r in reader if r["type"] == type.name]

    def reply(self, request: Request):
        if intents.GAME_QUESTION in request.intents:
            question_type = QuestionType.from_request(request, intents.GAME_QUESTION)
        elif state.QUESTION_TYPE in request.state_session:
            question_type = QuestionType.from_state(request)
        else:
            question_type = QuestionType.simple
        questions = self.get_questions(question_type)
        asked = set(request.state_session.get(state.ASKED_QUESTIONS, []))
        not_asked = [q for q in questions if q["id"] not in asked]
        if not_asked:
            question = random.choice(not_asked)
            question_id = question["id"]
            question_text = question["text"]
            self._next_scene = AnswerScene()
            return self.make_response(
                request,
                f"Задаю {question_type.russian()} вопрос. {question_text}",
                state={
                    "question_id": question_id,
                    state.ASKED_QUESTIONS: list(asked) + [question_id],
                },
                buttons=[button(question["answer"])],
            )
        else:
            # TODO сделать более плавный UX
            # например предложить пользователю категорию,
            # в которой еще остались вопросы
            text = (
                "Вы ответили на все вопросы этой категории!"
                "Я могу провести экскурсию по памятнику "
                "могу рассказать, про каждую фигуру на памятнике "
                "а можем сыграть в викторину"
            )
            return self.make_response(
                request,
                text,
                buttons=[
                    button("Сыграть в викторину"),
                    button("Расскажи экскурсию"),
                ],
            )

    def handle_local_intents(self, request: Request):
        if intents.START_TOUR in request.intents:
            return StartTour()
        elif intents.START_GAME in request.intents:
            return StartGame()
        else:
            return AnswerScene()


class AnswerScene(GlobalScene):
    @staticmethod
    def get_question(id: int):
        with open("guide/questions.csv", mode="r", encoding="utf-8") as in_file:
            reader = csv.DictReader(in_file, delimiter=",")
            return [r for r in reader if r["id"] == id][0]

    def reply(self, request: Request):
        question_id = request.state_session["question_id"]
        question = self.get_question(question_id)
        # TODO поддержать нечисловые типы ответов для вопросов
        # TODO поддержать частично правильный ответ
        correct_answer = int(question["answer"])
        nlu_entities = request.request_body["request"]["nlu"]["entities"]
        nlu_numbers = [e["value"] for e in nlu_entities if e["type"] == "YANDEX.NUMBER"]
        answered_correctly = correct_answer in nlu_numbers
        text = question["reply_true"] if answered_correctly else question["reply_false"]
        next_question_prompt = {
            "simple": "Задать еще простой вопрос?",
            "hard": "Задать еще сложный вопрос?",
            "attention": "Задать еще вопрос на внимательность?",
        }[question["type"]]
        return self.make_response(
            request,
            f"{text} {next_question_prompt}",
            buttons=[button("Да"), button("Нет")],
            state={state.QUESTION_TYPE: question["type"]},
        )

    def handle_local_intents(self, request: Request):
        if intents.CONFIRM in request.intents:
            return QuestionScene()
        elif intents.GAME_QUESTION in request.intents:
            return QuestionScene()
        elif intents.REJECT in request.intents:
            return Welcome()


class WhoIs(GlobalScene):
    @staticmethod
    def __get_info(id: str):
        with open("guide/persons.csv", mode="r", encoding="utf-8") as in_file:
            reader = csv.DictReader(in_file, delimiter=",")
            return [r for r in reader if r["id"] == id][0]

    def reply(self, request: Request):
        persona = request.intents[intents.TELL_ABOUT]["slots"]["who"]["value"]
        previous = request.state_session.get("scene", "")
        data = self.__get_info(persona)
        text = data["short"] + "\nПродолжим?"
        card = image_gallery(image_ids=data["gallery"].split(sep="|"))

        return self.make_response(
            request, text, card=card, state={"previous": previous}
        )

    def handle_local_intents(self, request: Request):
        if intents.CONFIRM in request.intents:
            return eval(request.state_session["previous"] + "()")
        elif intents.REJECT in request.intents:
            return Welcome()


def _list_scenes():
    current_module = sys.modules[__name__]
    scenes = []
    for name, obj in inspect.getmembers(current_module):
        if inspect.isclass(obj) and issubclass(obj, Scene):
            scenes.append(obj)
    return scenes


SCENES = {scene.id(): scene for scene in _list_scenes()}

DEFAULT_SCENE = Welcome