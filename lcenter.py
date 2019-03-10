#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import json
import logging
import os
import ssl
import time
import urllib.request
from multiprocessing.dummy import Pool as ThreadPool

import bs4
import telegram.ext as telegram

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)

logger = logging.getLogger(__name__)

LCENTER_CHECK_RECEPTION_URL = "https://www.lcenter.ru/by_registry/tickets/ajax/{day_timestamp}/{doctor_id}"

# key: doctor id, value: doctor name
doctors_ids = {
    "132/237": "Boginya Olga Viktorovna",
}

# key: doctor id, value: dates
monitoring_doctors_reception_days = {
    "132/237": [
        "1534107600",  # 13 Aug
    ]
}


def get_date_from_timestamp(timestamp):
    return datetime.datetime.fromtimestamp(
        int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')


def is_interval_actual(interval):
    if "class" in interval.attrs and interval.attrs["class"] == ["busy-date"]:
        return False

    current_date = datetime.datetime.now()
    intervale_date = current_date.replace(
        hour=int(interval.string.split(":")[0]),
        minute=int(interval.string.split(":")[1]) + 5,
        second=0)
    return intervale_date > current_date


def parse_raw_intervals(raw_intervals):
    return [
        get_date_from_timestamp(interval.attrs["data-time"])
        for interval in raw_intervals
    ]


def get_empty_receptions_for_current_day(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    for key, value in {
            'Accept':
            'application/json, text/javascript, */*; q=0.01',
            'Accept-Encoding':
            'gzip, deflate, br',
            'Accept-Language':
            'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection':
            'keep-alive',
            # 'Content-Length': '13935',
            'Content-Type':
            'application/x-www-form-urlencoded; charset=UTF-8',
            'Cookie':
            'has_js=1; _ym_uid=1527500038769581494; SLO_GWPT_Show_Hide_tmp=1; SLO_wptGlobTipTmp=1; collapsiblock=%7B%20%20%7D; _ym_d=1529922082; auth-fio=%D0%9E%D1%85%D0%BE%D0%BD%D1%86%D0%B5%D0%B2+%D0%90%D0%BD%D1%82%D0%BE%D0%BD+%D0%90%D0%BB%D0%B5%D0%BA%D1%81%D0%B5%D0%B5%D0%B2%D0%B8%D1%87; by_intro_disable=%7B%226%22%3Afalse%2C%22global%22%3Afalse%2C%225%22%3Afalse%7D; _ym_isad=1; _ym_visorc_21079270=w; reviews-block_3=1; reviews-block_2=1; departments-block_3=10',
            'DNT':
            '1',
            'Host':
            'www.lcenter.ru',
            'Origin':
            'https://www.lcenter.ru',
            'Referer':
            'https://www.lcenter.ru/doctor/boginya-olga-viktorovna',
            'User-Agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.170 Safari/537.36 OPR/53.0.2907.99',
            'X-Requested-With':
            'XMLHttpRequest'
    }.items():
        req.add_header(key, value)
    resp = urllib.request.urlopen(req, context=ctx)
    content = resp.read()

    j = json.loads(content)

    parsed_html = bs4.BeautifulSoup(markup=j[2]['data'], features="html.parser")
    try:
        intervals = parsed_html.body.find('ul').contents
    except AttributeError:
        raise AttributeError("Cannot find interval in url response. Check url correctness: {}".format(
            url))

    intervals = [
        interval for interval in intervals if is_interval_actual(interval)
    ]
    intervals = parse_raw_intervals(intervals)

    print(intervals)
    return intervals


def notify_about_available_reception(bot, doctor_id, receptions_info):
    # The notifier function
    def notify(title, subtitle, message):
        t = '-title {!r}'.format(title)
        s = '-subtitle {!r}'.format(subtitle)
        m = '-message {!r}'.format(message)
        os.system('terminal-notifier {}'.format(' '.join(
            [m, t, s, '-ignoreDnD'])))

    # Prepare message
    message = "{doctor_name}\n{dates}".format(
        dates=' ,'.join(receptions_info), doctor_name=doctors_ids[doctor_id])
    # Calling the function
    notify(
        title="A new medical record is available",
        subtitle="in lcenter",
        message=message)

    bot.send_message(chat_id=207729481, text=message)


# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.
def start(bot, update):
    update.message.reply_text('Hi! Use /set <seconds> to set a timer')


def alarm(bot, job):
    """Send the alarm message."""
    bot.send_message(job.context, text='Beep!')


def set_timer(bot, update, args, job_queue, chat_data):
    """Add a job to the queue."""
    chat_id = update.message.chat_id
    try:
        # args[0] should contain the time for the timer in seconds
        due = int(args[0])
        if due < 0:
            update.message.reply_text('Sorry we can not go back to future!')
            return

        # Add job to queue
        job = job_queue.run_once(alarm, due, context=chat_id)
        chat_data['job'] = job

        update.message.reply_text('Timer successfully set!')

    except (IndexError, ValueError):
        update.message.reply_text('Usage: /set <seconds>')


def unset(bot, update, chat_data):
    """Remove the job if the user changed their mind."""
    if 'job' not in chat_data:
        update.message.reply_text('You have no active timer')
        return

    job = chat_data['job']
    job.schedule_removal()
    del chat_data['job']

    update.message.reply_text('Timer successfully unset!')


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


def start_telegram_bot():
    updater = telegram.Updater("576999277:AAGFOfw8WUOz2FB-TGgTVkNjBdkLZC1AAUU")

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(telegram.CommandHandler("start", start))
    dp.add_handler(telegram.CommandHandler("help", start))
    dp.add_handler(
        telegram.CommandHandler(
            "set",
            set_timer,
            pass_args=True,
            pass_job_queue=True,
            pass_chat_data=True))
    dp.add_handler(
        telegram.CommandHandler("unset", unset, pass_chat_data=True))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Block until you press Ctrl-C or the process receives SIGINT, SIGTERM or
    # SIGABRT. This should be used most of the time, since start_polling() is
    # non-blocking and will stop the bot gracefully.
    pool = ThreadPool(1)
    pool.map(updater.idle, [])

    return updater


def process():
    bot_updater = start_telegram_bot()
    try:
        while True:
            for doctor_id, monitoring_days in monitoring_doctors_reception_days.items(
            ):
                for monitoring_day in monitoring_days:
                    try:
                        url = LCENTER_CHECK_RECEPTION_URL.format(
                            doctor_id=doctor_id, day_timestamp=monitoring_day)
                        empty_receptions = get_empty_receptions_for_current_day(
                            url)
                        if empty_receptions:
                            notify_about_available_reception(
                                bot_updater.bot, doctor_id, empty_receptions)
                    except Exception as e:
                        print("Hey! You have got an error here: {}".format(e))
                    time.sleep(15)
    except KeyboardInterrupt:
        bot_updater.stop()


if __name__ == '__main__':
    process()
