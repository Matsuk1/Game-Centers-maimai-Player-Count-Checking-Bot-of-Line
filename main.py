import gc
import random
import socket
import requests
import json
import re
import sys
import subprocess
import time
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

center_list = "./configs/center_list.json"
config_list = "./configs/bot_config.json"

app = Flask(__name__)

with open(config_list, 'r', encoding='utf-8') as config_file:
    bot_config = json.load(config_file)
config_file.close()

LINE_CHANNEL_ACCESS_TOKEN = bot_config['line_config']['channel_token']
LINE_CHANNEL_SECRET = bot_config['lind_config']['channel_secret']
bind_port = bot_config['bind_port']

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

def timestamp_to_hms(timestamp):
    dt = datetime.fromtimestamp(timestamp+9*3600)
    return dt.strftime("%H:%M:%S")

def read_center():
    global center
    with open(center_list, 'r', encoding='utf-8') as file:
        center = json.load(file)
    file.close()

def get_num_of_people():
    global center
    num_of_people = 0
    updated = False
    result = "これは現在、山梨県内のゲームセンターの人数状況ですよ!\n-------------------------\n"
    read_center()
    for key, value in center.items():
        if value['last_time'] :
            result += f"{key}: {value['num']}（{timestamp_to_hms(value['last_time'])}）\n"
            num_of_people += value['num']
            updated = True
    if not updated :
        result = "まだ誰も人数状況を更新していません··"
    else :
        result += f"-------------------------\n現在、全てのゲームセンターに合計で{num_of_people}人いますよ！"
    return result

def get_num_of_center(ctnm):
    read_center()
    found = False
    for key, value in center.items():
        if ctnm in value["nknm"]:
            found = True
            if value['last_time'] :
                result = f"{key}: {value['num']}（{timestamp_to_hms(value['last_time'])}）"
            else :
                result = f"{key}: まだ誰も人数状況を更新していません··"
            break
    if found :
        return result
    else :
        return "このゲームセンターが見つかりません··"

def update_num(user_id, cmd):
    global center
    read_center()
    type = 0
    match = re.search(r'(\d+)$', cmd)
    new_num = int(match.group(1))
    ctnm = cmd[:-len(match.group(1))].strip()
    if ctnm.endswith("+"):
        type = 1
        ctnm = ctnm[:-1]
    elif ctnm.endswith("-"):
        type = 2
        ctnm = ctnm[:-1]
    elif ctnm.endswith("="):
        type = 3
        ctnm = ctnm[:-1]

    found = False
    for key, value in center.items():
        if ctnm in value["nknm"]:
            found = True
            value['last_time'] = time.time()
            if type == 1:
                new_num = value['num'] + new_num
            elif type == 2:
                new_num = value['num'] - new_num
            if new_num < 0:
                new_num = 0
            user_name = line_bot_api.get_profile(user_id).display_name
            value['people'] += f"{user_name}: {value['num']}->{new_num}（{timestamp_to_hms(value['last_time'])}）\n"
            result = f"[UPDATED]\n{key}: {value['num']}->{new_num}（{timestamp_to_hms(value['last_time'])}）"
            value['num'] = new_num
            break

    with open(center_list, "w", encoding="utf-8") as file:
        json.dump(center, file, ensure_ascii=False, indent=4)
    file.close();

    if found :
        return result
    else :
        return "このゲームセンターが見つかりません··"

def get_nickname(ctnm):
    global center
    read_center()
    found = False

    for key, value in center.items():
        if ctnm in value["nknm"]:
            found = True
            nknm_list = '\n - '.join(value['nknm'])
            result = f"{key}のニックネーム:\n - {nknm_list}"
            break

    if found :
        return result
    else :
        return "このゲームセンターが見つかりません··"

def get_people(ctnm):
    global center
    read_center()
    found = False

    for key, value in center.items():
        if ctnm in value["nknm"]:
            found = True
            if value['last_time'] :
                result = f"{key}:\n{value['people'][:-1]}"
            else:
                result = f"{key}: まだ誰も人数状況を更新していません··"
            break

    if found :
        return result
    else :
        return "このゲームセンターが見つかりません··"

def clear_center():
    global center
    read_center()

    for key, value in center.items():
        value['last_time'] = 0
        value['num'] = 0
        value['people'] = ""
        with open(center_list, "w", encoding="utf-8") as file:
            json.dump(center, file, ensure_ascii=False, indent=4)
        file.close();
        result = "完成しました！"

    return result

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

    need_reply = False

    if user_message.strip() == "人数チェック":
        reply_message = get_num_of_people()
        need_reply = True

    elif user_message.strip().endswith(("何人","どう")):
        reply_message = get_num_of_center(user_message.strip()[:-2])
        need_reply = True

    elif user_message.strip().endswith("人"):
        reply_message = update_num(user_id, user_message.strip()[:-1])
        need_reply = True

    elif user_message.strip().endswith("ニック"):
        reply_message = get_nickname(user_message.strip()[:-3])
        need_reply = True

    elif user_message.strip().endswith("誰"):
        reply_message = get_people(user_message.strip()[:-1])
        need_reply = True

    elif user_message.strip() == "confirm clearing" :
        reply_message = clear_center()
        need_reply = True

    if need_reply :
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_message)
        )

if __name__ == "__main__":
    app.run(port = bind_port)
