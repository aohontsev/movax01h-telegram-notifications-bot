# -*- coding: utf-8 -*-
import flask
import lcenter

TEXT = '''<html>\n<head> <title>movax01h telegram bot</title> </head>\n<body>'''


def get_app():
    application = flask.Flask(__name__)
    application.add_url_rule('/', 'index', (lambda: TEXT))
    return application


if __name__ == "__main__":
    lcenter.process()
    app = get_app()
    app.run()


