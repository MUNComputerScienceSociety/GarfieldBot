import re
import os
import json

import requests
from bs4 import BeautifulSoup

from GarfieldBot import GarfieldPlugin, MessageEvent


class CourseEmbed(GarfieldPlugin):
    """
    Allows users to easily embed information about a certain course.
    """

    def __init__(self, manifest, bot):
        super().__init__(manifest, bot)
        self._re = re.compile(r"\[(\D+)(\w+)\]")
        self._courses = {}

        with open(os.path.join(manifest["path"], "listings.json")) as f:
            listings = json.load(f)
        for dep, url in listings.items():
            self._parse_listings(url, dep)

        self.bot.register_handler("message", self.handle_message)

    def _parse_listings(self, url: str, department: str) -> None:
        self._courses[department] = {}
        resp = requests.get(url)
        soup = BeautifulSoup(resp.text, features="lxml")
        course_divs = soup.find_all("div", {"class": "course"})
        for course_div in course_divs:
            number = course_div.find("p", {"class": "courseNumber"}).getText().strip()
            name = course_div.find("p", {"class": "courseTitle"}).getText().strip()
            desc = course_div.find("div", {"class": "courseDesc"}).find("p").getText().strip()
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
