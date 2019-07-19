#!/usr/bin/env python
import os
import ast
import re
import json
import tempfile
import zipfile
from math import ceil
from bs4 import BeautifulSoup
from urllib.parse import unquote
from collections import OrderedDict
from ricecooker.utils import downloader
from ricecooker.chefs import SushiChef
from ricecooker.classes.files import YouTubeVideoFile
from ricecooker.config import LOGGER  # Use LOGGER to print messages
from ricecooker.exceptions import raise_for_invalid_channel
from ricecooker.classes.nodes import TopicNode, VideoNode
from ricecooker.classes.licenses import CC_BY_NC_SALicense
from ricecooker.utils.zip import create_predictable_zip


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
BASE_URL = "https://learndigital.withgoogle.com/garagedigital/{}"


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
    # Your chef subclass can override/extend the following method:
    # get_channel: to create ChannelNode manually instead of using channel_info
    # pre_run: to perform preliminary tasks, e.g., crawling and scraping website
    # __init__: if need to customize functionality or add command line arguments

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
        # resp = downloader.read(BASE_URL.format("courses")).decode("utf-8")
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
            course_node = TopicNode(
                source_id=course["title"],
                title=course["title"],
                thumbnail=course["image"],
            )
            course_url = "{base}course/{slug}?enroll-success=1".format(
                base=BASE_URL, slug=course["slug"]
            )
            categories[course["category"]].add_child(course_node)
            self.parse_course(course_node, course_url)

    def parse_course(self, course, url):
        LOGGER.info("Parsing course {}...".format(course.title))
        # resp = downloader.read(url).decode("utf-8")
        with open("course", "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            modules = page.find_all("a", {"data-gtm-tag": "module-card module-link"})
            for module in modules:
                module_url = BASE_URL.format(module["href"])
                thumbnail = module.find("img", class_="module-info__image")["src"]
                title = module.find("img", class_="module-info__image")["alt"]

                module_node = TopicNode(
                    source_id=title, title=title, thumbnail=thumbnail
                )
                course.add_child(module_node)
                self.parse_module(module_node, module_url)

    def parse_module(self, module, url):
        LOGGER.info("Parsing module {}...".format(module.title))
        # resp = downloader.read(url).decode("utf-8")
        with open("module", "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            lessons = page.find_all(
                "div",
                class_="myg-topic-sidenav__accordion accordion__item js-accordion-item",
            )
            for lesson in lessons:
                title = lesson.find("h3").text.split(". ")[1]
                lesson_url = (
                    lesson.find("a", class_="accordion__panel--item")["ng-click"]
                    .split("'")[1]
                    .split("\\")[0]
                )
                practice_url = lesson_url + "practice"

                lesson_node = TopicNode(source_id=title, title=title)
                module.add_child(lesson_node)
                self.add_lesson_video(lesson_node, lesson_url)
                self.add_lesson_practice(lesson_node, practice_url)

                exam_url = "{}/assessment".format(url)
                self.add_exam(module, exam_url)

    def add_lesson_video(self, lesson, url):
        LOGGER.info("Adding video for the course {}...".format(lesson.title))
        # resp = downloader.read(url).decode("utf-8")
        with open("video", "r") as resp:
            page = BeautifulSoup(resp, "html.parser")
            video_id = page.find("div", {"youtube-api": "lesson.youtubeApi"})[
                "video-id"
            ]
            title = "{} Video".format(lesson.title)

            video_file = YouTubeVideoFile(
                youtube_id=video_id, high_resolution=True, language=CHANNEL_LANGUAGE
            )
            video_node = VideoNode(
                source_id=title,
                title=title,
                license=CC_BY_NC_SALicense(copyright_holder="Google Garage Digital"),
                language=CHANNEL_LANGUAGE,
                files=[video_file],
            )
            lesson.add_child(video_node)

    def add_lesson_practice(self, lesson, url):
        LOGGER.info("Adding practice for the course {}...".format(lesson.title))
        # resp = downloader.read(url).decode("utf-8")
        # page = BeautifulSoup(resp, "html.parser")

    def add_exam(self, module, url):
        LOGGER.info("Adding exam for the module {}...".format(module.title))


# CLI
################################################################################
if __name__ == "__main__":
    # This code runs when sushichef.py is called from the command line
    chef = GoogleGarageDigitalChef()
    chef.main()
