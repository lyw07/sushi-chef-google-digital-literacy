#!/usr/bin/env python
import re
import json
from bs4 import BeautifulSoup
from ricecooker.utils import downloader
from ricecooker.chefs import SushiChef
from ricecooker.classes.files import YouTubeVideoFile
from ricecooker.config import LOGGER
from ricecooker.exceptions import raise_for_invalid_channel
from ricecooker.classes.nodes import TopicNode, VideoNode, ExerciseNode
from ricecooker.classes.licenses import CC_BY_NC_SALicense
from ricecooker.classes.questions import SingleSelectQuestion, MultipleSelectQuestion
from le_utils.constants import exercises


# Run constants
################################################################################
CHANNEL_NAME = "Google Garage Digital"  # Name of channel
CHANNEL_SOURCE_ID = "sushi-chef-google-digital-literacy"  # Channel's unique id
CHANNEL_DOMAIN = "learndigital.withgoogle.com"  # Who is providing the content
CHANNEL_LANGUAGE = "es"  # Language of channel
CHANNEL_DESCRIPTION = ""  # Description of the channel (optional)
CHANNEL_THUMBNAIL = None  # Local path or url to image file (optional)

# Additional constants
################################################################################
BASE_URL = "https://learndigital.withgoogle.com/garagedigital/"
TOKEN_URL = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={key}"
SIGN_IN_URL = "https://learndigital.withgoogle.com/garagedigital/modules/gitkit/widget?mode=select"


# The chef subclass
################################################################################
class GoogleGarageDigitalChef(SushiChef):
    """
    This class uploads the Google Garage Digital channel to Kolibri Studio.
    Your command line script should call the `main` method as the entry point,
    which performs the following steps:
      - Parse command line arguments and options (run `./sushichef.py -h` for details)
      - Call the `SushiChef.run` method which in turn calls `pre_run` (optional)
        and then the ricecooker function `uploadchannel` which in turn calls this
        class' `get_channel` method to get channel info, then `construct_channel`
        to build the contentnode tree.
    For more info, see https://github.com/learningequality/ricecooker/tree/master/docs
    """

    channel_info = {  # Channel Metadata
        "CHANNEL_SOURCE_DOMAIN": CHANNEL_DOMAIN,  # Who is providing the content
        "CHANNEL_SOURCE_ID": CHANNEL_SOURCE_ID,  # Channel's unique id
        "CHANNEL_TITLE": CHANNEL_NAME,  # Name of channel
        "CHANNEL_LANGUAGE": CHANNEL_LANGUAGE,  # Language of channel
        "CHANNEL_THUMBNAIL": CHANNEL_THUMBNAIL,  # Local path or url to image file (optional)
        "CHANNEL_DESCRIPTION": CHANNEL_DESCRIPTION,  # Description of the channel (optional)
    }

    cookies = {}

    def pre_run(self, *args, **kwargs):
    #     # Get the browser api key
    #     resp = downloader.read(SIGN_IN_URL).decode("utf-8")
    #     page = BeautifulSoup(resp, "html.parser")
    #     api_key = page.find("div", {"data-title": "Please sign in"})["data-browser-api-key"]

    #     # Get the id token
    #     data = {"email": "channeladmin@learningequality.org", "password": "1234567890"}
    #     get_token_url = TOKEN_URL.format(key=api_key)
    #     result = downloader.DOWNLOAD_SESSION.post(get_token_url, data=data).content.decode("utf-8")
    #     token = json.loads(result)["idToken"]

        # Set cookies for the session

        self.cookies = {"gtoken": token}

    def construct_channel(self, *args, **kwargs):
        """
        Creates ChannelNode and build topic tree
        Args:
          - args: arguments passed in during upload_channel (currently None)
          - kwargs: extra argumens and options not handled by `uploadchannel`.
            For example, add the command line option   lang="fr"  and the string
            "fr" will be passed along to `construct_channel` as kwargs['lang'].
        Returns: ChannelNode
        """
        channel = self.get_channel(
            *args, **kwargs
        )  # Create ChannelNode from data in self.channel_info

        LOGGER.info("Starting to scrape the channel...")
        # Parse the index page to get the topics
        # resp = downloader.make_request("{}courses".format(BASE_URL), cookies=self.cookies).content.decode("utf-8")
        with open("coursepage", "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            self.parse_page(channel, page)

            raise_for_invalid_channel(
                channel
            )  # Check for errors in channel construction
            return channel

    def parse_page(self, channel, page):
        categories = {}

        # Create TopicNodes for each filter
        filters = page.find("nav", class_="course-list__filters").find_all("a")
        for category in filters:
            category_id = category["data-filterby"]
            # Exclude the filter which contains all the courses
            if category_id == "all":
                continue

            category_node = TopicNode(source_id=category.text, title=category.text)
            categories[category_id] = category_node
            channel.add_child(category_node)

        # Get all the courses in json format
        data = page.find("script", {"id": "__data__"}).text
        pattern = re.compile("courses: \[(.*?)}]")
        courses = pattern.search(data).group(1).split("}, ")
        for item in courses:
            course = json.loads(item + "}")
            course_url = "{base}course/{slug}?enroll-success=1".format(
                base=BASE_URL, slug=course["slug"]
            )
            course_node = TopicNode(
                source_id="{lang}-{course}".format(lang=CHANNEL_LANGUAGE, course=course["slug"]),
                title=course["title"],
                thumbnail=course["image"],
            )
            categories[course["category"]].add_child(course_node)
            self.parse_course(course_node, course_url)

    def parse_course(self, course, url):
        LOGGER.info("=========================================")
        LOGGER.info("Parsing course {}...".format(course.title))
        # resp = downloader.make_request(url, cookies=self.cookies).content.decode("utf-8")
        file_path = "files/{}.txt".format(course.title)
        with open(file_path, "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            modules = page.find_all("a", {"data-gtm-tag": "module-card module-link"})
            for module in modules:
                module_url = "{base}{module}".format(base=BASE_URL, module=module["href"])
                thumbnail = module.find("img", class_="module-info__image")["src"]
                title = module.find("img", class_="module-info__image")["alt"]
                source_id = "{lang}-{module}".format(lang=CHANNEL_LANGUAGE, module=module["href"].replace("/", "-"))
                module_node = TopicNode(
                    source_id=source_id, title=title, thumbnail=thumbnail
                )
                course.add_child(module_node)
                self.parse_module(module_node, module_url, course.title)

    def parse_module(self, module, url, course_title):
        LOGGER.info("=========================")
        LOGGER.info("Parsing module {}...".format(module.title))
        # resp = downloader.make_request(url,cookies=self.cookies).content.decode("utf-8")
        file_path = "files/{}/{}.txt".format(course_title, module.title)
        with open(file_path, "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            lessons = page.find_all(
                "div",
                class_="myg-topic-sidenav__accordion accordion__item js-accordion-item",
            )
            for lesson in lessons:
                title = lesson.find("h3").text.split(". ")[1]
                lesson_tag = lesson.find("a", class_="accordion__panel--item")
                lesson_url = lesson_tag["ng-click"].split("'")[1].split("\\")[0]
                practice_url = lesson_url + "practice"

                video_title = lesson_tag.find("h4", class_="accordion__panel--item-title")
                practice_title = video_title.find_next("h4", class_="accordion__panel--item-title")

                source_id = "{lang}-{lesson}".format(lang=CHANNEL_LANGUAGE, lesson=lesson_url.split("course/")[-1].replace("#/", "").replace("/", "-"))
                lesson_node = TopicNode(source_id=source_id, title=title)
                module.add_child(lesson_node)
                self.add_lesson_video(lesson_node, lesson_url, video_title.text, course_title, module.title)
                self.add_lesson_practice(lesson_node, practice_url, practice_title.text, course_title, module.title)

            exam_url = "{}/assessment".format(url)
            self.add_exam(module, exam_url)

    def add_exam(self, module, url):
        LOGGER.info("Adding exam for the module {}...".format(module.title))
        # resp = downloader.make_request(url, cookies=self.cookies).content.decode("utf-8")
        # page = BeautifulSoup(resp, "html.parser")

    def add_lesson_video(self, lesson, url, title, course_title, module_title):
        LOGGER.info("Adding video for the course {}...".format(lesson.title))
        # resp = downloader.make_request(url, cookies=self.cookies).content.decode("utf-8")
        file_path = "files/{}/{}/{}/{}-video.txt".format(course_title, module_title, lesson.title, title)
        with open(file_path, "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            video_id = page.find("div", {"youtube-api": "lesson.youtubeApi"})[
                "video-id"
            ]
            source_id = "{}-video".format(lesson.source_id)

            video_file = YouTubeVideoFile(
                youtube_id=video_id, high_resolution=True, language=CHANNEL_LANGUAGE
            )
            video_node = VideoNode(
                source_id=source_id,
                title=title,
                license=CC_BY_NC_SALicense(copyright_holder="Google Garage Digital"),
                language=CHANNEL_LANGUAGE,
                files=[video_file],
            )
            lesson.add_child(video_node)

    def add_lesson_practice(self, lesson, url, title, course_title, module_title):
        LOGGER.info("Adding practice for the course {}...".format(lesson.title))
        # resp = downloader.make_request(url, cookies=self.cookies).content.decode("utf-8")
        file_path = "files/{}/{}/{}/{}-practice.txt".format(course_title, module_title, lesson.title, title)
        with open(file_path, "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            # Get the question description
            question_paras = page.find("div", class_="activity-intro__question").find_all("p")
            question_description = ""
            for description in question_paras:
                question_description = question_description + description.text + "\n"

            # Get the practice data to parse
            pattern = re.compile("window.lessonData = (.*;)")
            lesson_data = json.loads(pattern.search(page.text).group(1).replace(";", ""))
            practice_data = lesson_data["activities"][0]["activity"]
            practice_type = lesson_data["activities"][0]["type"]
            questions_add_to_exercise = []
            practice_id = "{}-practice".format(lesson.source_id)

            # A multiple select question
            if practice_type in ["select-right", "switches-text", "strike-through", "tag-cloud"]:
                questions_add_to_exercise.append(self.add_a_multiple_select_question(practice_data, question_description, practice_id))

            # A single select question
            elif practice_type in ["swipe-selector", "twitter-draganddrop", "image-slider"]:
                questions_add_to_exercise.append(self.add_a_single_select_question(practice_data, question_description, practice_id))

            # Multiple single select questions
            elif practice_type in ["text-drawer", "boolean-selector"]:
                questions_add_to_exercise = self.add_multiple_single_select_questions(practice_data["options"], question_description, practice_id)

            else:
                LOGGER.error("Type {} hasn't been analyzed: {}".format(practice_type, url))
                return

            # Create exercise node
            exercise_id = "{} Practice".format(lesson.title)
            exercise = ExerciseNode(
                source_id=exercise_id,
                title=title,
                license=CC_BY_NC_SALicense(copyright_holder="Google Garage Digital"),
                language=CHANNEL_LANGUAGE,
                thumbnail=None,
                exercise_data = {
                    "master_model": exercises.DO_ALL,
                    "randomize": False,
                },
                questions=questions_add_to_exercise,
            )
            lesson.add_child(exercise)

    def add_a_multiple_select_question(self, question, description, practice_id):
        all_answers = [choice["text"].replace("<p>", "").replace("</p>", "") for choice in question["options"]]
        correct_answers = []
        for correct_answer in question["correctOptions"]:
            correct_answers.append(all_answers[int(correct_answer)])
        question_node = MultipleSelectQuestion(id="{}-question".format(practice_id), question=description, correct_answers=correct_answers, all_answers=all_answers)

        return question_node

    def add_a_single_select_question(self, question, description, practice_id):
        all_answers = []
        for choice in question["options"]:
            if choice.get("text"):
                all_answers.append(choice["text"])
            else:
                all_answers.append("{value} {unit}".format(value=choice["value"], unit=question["unit"]))

        question_node = SingleSelectQuestion(id="{}-question".format(practice_id), question=description, correct_answer=all_answers[int(question["correctOption"])], all_answers=all_answers)

        return question_node

    def add_multiple_single_select_questions(self, questions, description, practice_id):
        result = []
        for question in questions:
            source_id = "{practice}-question-{q_index}".format(practice=practice_id, q_index=question["id"])
            all_answers = [(choice.get("answer") or choice.get("text")).replace("<p>", "").replace("</p>", "") for choice in question["options"]]
            question_text = description + "\n" + question["text"]
            question_node = SingleSelectQuestion(id=source_id, question=question_text, correct_answer=all_answers[int(question["correctOption"])], all_answers=all_answers)
            result.append(question_node)

        return result


# CLI
################################################################################
if __name__ == "__main__":
    # This code runs when sushichef.py is called from the command line
    chef = GoogleGarageDigitalChef()
    chef.main()
