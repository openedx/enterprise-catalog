"""
Defines the Kombu consumer for the enterprise_catalog project.
"""
from __future__ import absolute_import

from kombu import Exchange, Queue
from kombu.mixins import ConsumerMixin


class CatalogConsumer(ConsumerMixin):

    exchange = Exchange('catalog', type='direct')
    queues = [
        Queue('program_create_queue', exchange, routing_key='catalog.program.create'),
        Queue('program_update_queue', exchange, routing_key='catalog.program.update'),
        Queue('program_delete_queue', exchange, routing_key='catalog.program.delete'),
        Queue('course_update_queue', exchange, routing_key='catalog.course.update'),
        Queue('courserun_update_queue', exchange, routing_key='catalog.courserun.update')
    ]

    def __init__(self, connection):
        self.connection = connection

    def get_consumers(self, Consumer, channel):
        return [
            Consumer(self.queues, callbacks=[self.on_message], accept=['json']),
        ]

    def on_message(self, body, message):
        print(message)
        print('RECEIVED MESSAGE: {0!r}'.format(body))
        message.ack()
