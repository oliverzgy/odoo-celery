# -*- coding: utf-8 -*-

from odoo import models, api


class Base(models.AbstractModel):
    """The base model, which is implicitly inherited by all models.

    A new :meth:`~with_delay` method is added on all Odoo Models, allowing to
    postpone the execution of a job method in an asynchronous process.
    """
    _inherit = 'base'

    def with_celery(self, method, *args, **kwargs):
        celery = {
            'countdown': 0, 'retry': False,
            'retry_policy': {'max_retries': 2, 'interval_start': 2}
        }
        celery_task_vals = {
            'ref': '%s.%s' % (self._name, method.__name__)
        }

        if hasattr(method, '_api') and method._api in ['model']:
            self.env["celery.task"].call_task(self._name, method.__name__, args=[*args],
                                              context=dict(self._context),
                                              celery_task_vals=celery_task_vals, celery=celery,
                                              transaction_strategy='immediate', **kwargs)
        else:
            self.env["celery.task"].call_task(self._name, method.__name__, args=[self.id, *args],
                                              context=dict(self._context),
                                              celery_task_vals=celery_task_vals, celery=celery,
                                              transaction_strategy='immediate', **kwargs)
        return True