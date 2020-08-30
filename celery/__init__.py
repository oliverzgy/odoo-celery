# Copyright Nova Code (http://www.novacode.nl)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)

from . import odoo
from . import fields
from . import models
from . import report
from . import wizard

import logging
import os
import time
from threading import Thread
from subprocess import Popen, PIPE
from odoo.service import server
from odoo.tools import config


_logger = logging.getLogger(__name__)


class CeleryJob(object):

    def __init__(self):
        self.restart = True

    def poll(self):
        return None

    def env(self):
        celery_broker = os.environ.get('ODOO_CELERY_BROKER') or config.misc.get("celery", {}).get(
            'celery_broker') or config.get('celery_broker') or "amqp://guest@localhost//"
        celery_queue = config.misc.get("celery", {}).get(
            'celery_queue') or config.get('celery_queue') or 'celery_queue'
        flower_user = (os.environ.get('ODOO_CELERY_USER') or config.misc.get("celery", {}).get('flower_user') or config.get(
            'flower_user'))
        flower_password = (os.environ.get('ODOO_CELERY_PASSWORD') or config.misc.get("celery", {}).get(
            'flower_password') or config.get('flower_password'))
        flower_port = (os.environ.get('ODOO_CELERY_FLOWER_PORT') or config.misc.get("celery", {}).get(
                    'flower_port') or config.get('flower_port')) or '5555'

        env = dict(os.environ)
        env.update({
            'ODOO_CELERY_BROKER': celery_broker,
            'ODOO_CELERY_QUEUE': celery_queue,
            'ODOO_CELERY_FLOWER_USER': flower_user,
            'ODOO_CELERY_FLOWER_PASSWORD': flower_password,
            'ODOO_CELERY_FLOWER_PORT': flower_port
        })
        return env

    def start_celery(self, path):
        if self.restart:
            env = self.env()
            p = Popen(["celery", "-A", "odoo", "worker", "--loglevel=info", "-Q", env.get('ODOO_CELERY_QUEUE'), "-n",
                       env.get('ODOO_CELERY_QUEUE')], cwd=path, env=env, stdin=PIPE)  # env pass the broker and queue
            return p
        else:
            return self

    def start_flower(self, path):
        if self.restart:
            env = self.env()
            user = env.get('ODOO_CELERY_FLOWER_USER')
            password = env.get('ODOO_CELERY_FLOWER_PASSWORD')
            port = env.get('ODOO_CELERY_FLOWER_PORT')
            f = Popen(["celery", "flower", "-A", "odoo", "--port=%s" % port, "--basic_auth=%s:%s" % (user, password)], cwd=path, env=env, stdin=PIPE)  # env pass the broker and queue
            return f
        else:
            return self

    def check_status(self):
        path = os.path.abspath(os.path.dirname(__file__))
        c = self.start_celery(path)
        time.sleep(3)  # after celery start, otherwise cause some error
        f = self.start_flower(path)
        while 1:
            if c.poll() is not None:
                c = self.start_celery(path)
            if f.poll() is not None:
                f = self.start_flower(path)
            time.sleep(10)

    def run(self):
        thr = Thread(name='odoo_celery_thread', target=self.check_status)
        thr.daemon = True
        thr.start()

    def stop(self):
        self.restart = False


runner_thread = None

orig_prefork_start = server.PreforkServer.start
orig_prefork_stop = server.PreforkServer.stop
orig_threaded_start = server.ThreadedServer.start
orig_threaded_stop = server.ThreadedServer.stop


def prefork_start(server, *args, **kwargs):
    global runner_thread
    res = orig_prefork_start(server, *args, **kwargs)
    if not config['stop_after_init']:
        _logger.info("starting celery job thread (in prefork server)")
        runner_thread = CeleryJob()
        runner_thread.run()
    return res


def prefork_stop(server, graceful=True):
    global runner_thread
    if runner_thread:
        runner_thread.stop()
    res = orig_prefork_stop(server, graceful)
    if runner_thread:
        runner_thread = None
    return res


def threaded_start(server, *args, **kwargs):
    global runner_thread
    res = orig_threaded_start(server, *args, **kwargs)
    if not config['stop_after_init']:
        _logger.info("starting celery job thread (in threaded server)")
        runner_thread = CeleryJob()
        runner_thread.run()
    return res


def threaded_stop(server):
    global runner_thread
    if runner_thread:
        runner_thread.stop()
    res = orig_threaded_stop(server)
    if runner_thread:
        runner_thread = None
    return res


server.PreforkServer.start = prefork_start
server.PreforkServer.stop = prefork_stop
server.ThreadedServer.start = threaded_start
server.ThreadedServer.stop = threaded_stop

