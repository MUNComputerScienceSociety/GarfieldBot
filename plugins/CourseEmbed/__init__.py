import re
import os
import json
import logging

import requests
from bs4 import BeautifulSoup

from GarfieldBot import GarfieldPlugin, MessageEvent


class CourseEmbed(GarfieldPlugin):
    """
    Allows users to easily embed information about a certain course.
    """

    def __init__(self, manifest, bot):
        super().__init__(manifest, bot)
        self._logger = logging.getLogger("CourseEmbed")
        self._re = re.compile(r"\[(\D+)(\w+)\]")
        self._courses = {}

        if os.path.isfile(os.path.join(manifest["path"], "courses.json")):
            with open(os.path.join(manifest["path"], "courses.json")) as f:
                self._courses = json.load(f)
            self._logger.info("Loaded courses.")
        else:
            self._logger.warning("No courses saved, generating now. This will take a while.")
            with open(os.path.join(manifest["path"], "listings.json")) as f:
                listings = json.load(f)
            for dep, url in listings.items():
                if isinstance(url, list):
                    for listing_url in url:
                        self._logger.info(f"Retrieving {dep} from {listing_url}...")
                        self._parse_listings(listing_url, dep)
                else:
                    self._logger.info(f"Retrieving {dep} from {url}...")
                    self._parse_listings(url, dep)
            with open(os.path.join(manifest["path"], "courses.json"), "w") as f:
                json.dump(self._courses, f)
            self._logger.info("Courses generated.")

        self.bot.register_handler("message", self.handle_message)

    def _parse_listings(self, url: str, department: str) -> None:
        if department not in self._courses:
            self._courses[department] = {}
        resp = requests.get(url)
        soup = BeautifulSoup(resp.text, features="lxml")
        course_divs = soup.find_all("div", {"class": "course"})
        for course_div in course_divs:
            # print(course_div.getText())
            number = course_div.find("p", {"class": "courseNumber"}).getText().strip()
            name = course_div.find("p", {"class": "courseTitle"}).getText().strip()
            try:
                desc = course_div.find("div", {"class": "courseDesc"}).find("p").getText().strip()
            except AttributeError:
                desc = ""
            attrs = []
            for attr in course_div.find_all("p", {"class": "courseAttrs"}):
                attr_text = attr.getText().strip()
                key_replacement = {
                    "AR": "Attendance requirement",
                    "CH": "Credit hours",
                    "CO": "Co-requisite(s)",
                    "CR": "Credit restriction(s)",
                    "LC": "Lecture hours",
                    "LH": "Lab hours",
                    "OR": "Other requirement",
                    "PR": "Prerequisite(s)",
                    "UL": "Usage limitation(s)"
                }
                for key, value in key_replacement.items():
                    attr_text = attr_text.replace(f"{key}: ", f"*{value}:*\n")
                attrs.append(attr_text)
            self._courses[department][number] = {
                "name": name,
                "desc": desc,
                "attrs": attrs
            }

    def _generate_block(self, department: str, number: str) -> dict:
        block = {"type": "section", "fields": []}
        course = self._courses[department][number]
        block["fields"].append({
            "type": "mrkdwn",
            "text": f"*Course number*:\n{department}{number}"
        })
        block["fields"].append({
            "type": "mrkdwn",
            "text": f"*Course name:*\n{course['name']}"
        })
        # block["fields"].append({
        #     "type": "mrkdwn",
        #     "text": f"*Description:*\n{course['desc']}"
        # })
        for attr in course["attrs"]:
            block["fields"].append({
                "type": "mrkdwn",
                "text": attr
            })
        return block

    def handle_message(self, event: MessageEvent) -> None:
        matches = self._re.findall(event.text)
        blocks = []
        for match in matches:
            if len(blocks) != 0:
                blocks.append({
                    "type": "divider"
                })
            blocks.append(
                self._generate_block(*match)
            )
        if len(blocks) >= 1:
            self.bot.send_message(event.channel, "", blocks=blocks)
