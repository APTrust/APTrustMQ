import json
from io import BufferedReader

from kombu.mixins import ConsumerMixin
from kombu import Queue, Exchange

from dpnode.settings import DPNMQ
from dpnmq.handlers import broadcast_router, local_router
from dpnmq.messages import DPNMessageError

import logging
logger = logging.getLogger('dpnmq.console')

class DPNConsumer(ConsumerMixin):
    def __init__(self, conn, exchng, bcast_queue, bcast_rtkey, local_queue, local_rtkey, ignore_own=True):
        """A basic consumer that listens on DPN broadcast and local queues.

        :param conn:  Connection object to amqp server.
        :param exchng:  String of exchange to use on conn.
        :param bcast_queue:  String of broadcast queue name to use.
        :param bcast_rtkey:  String of broadcast routing key to use for message.
        :param local_queue:  String of the local queue name.
        :param local_rtkey:  String of the local routing key to use
        :param ignore_own:  Boolean weather to reply to your own messages.  Usually only test to False for testing.

        """
        self.connection = conn
        self.xchng = Exchange(exchng, 'topic', durable=True)
        self.bcast_queue = Queue(bcast_queue, exchange=self.xchng, routing_key=bcast_rtkey)
        self.direct_queue = Queue(local_queue, exchange=self.xchng, routing_key=local_rtkey)
        self.ignore_own = ignore_own

    def get_consumers(self, Consumer, chan):
        consumers = [
            Consumer(queues=[self.bcast_queue, ], callbacks=[self.route_broadcast, ], auto_declare=False),
            Consumer(queues=[self.direct_queue, ], callbacks=[self.route_local, ], auto_declare=False)
        ]
        return consumers

    # TODO when msg format is settled, validate message before processing to reduce all interior err msg raises.
    def _route_message(self, router, msg):
        """
        Sends the original message to the appropriate dispatcher provided by router.

        :param router:  TaskRouter instance to dispatch this message.
        :param msg: kombu.transport.base.Message to decode and dispatch.
        """
        try:
            decoded_body = json.loads(unicode(msg.body))
        except UnicodeDecodeError as err:
            raise DPNMessageError("Cannot Decode Message Body! %s" % err.message)

        try:
            message_name = decoded_body['message_name']
        except KeyError:
            raise DPNMessageError("Invalid message recieved with no 'message_body' set!")

        router.dispatch(message_name, msg, decoded_body)

    def route_local(self, body, msg):
        if self._ignore(msg):
            msg.reject()
            return None
        try:
            self._route_message(local_router, msg)
            logger.info("LOCAL MSG %s" % self._get_logentry(msg))
        except DPNMessageError as err:
            logger.info(err.message)

    def route_broadcast(self, body, msg):
        if self._ignore(msg):
            msg.reject()
            return None
        try:
            self._route_message(broadcast_router, msg)
            logger.info("BROADCAST MSG %s" % self._get_logentry(msg))
        except DPNMessageError as err:
            logger.info("DPN Message Error: %s" % err.message)

    def _get_logentry(self, msg):
        """
        Logs the receipt of a message from the queue.
        :param msg:  kombu.transport.base.Message instance.
        :return: None
        """
        # No validation at this point so form log whatever fields you can find.
        header_fields = ['from', 'reply_key', 'correlation_id', 'sequence']
        parts = ["%s: %s" % (field, msg.headers[field]) for field in header_fields if field in msg.headers]
        if not parts:
            return "Could Not Find Header Fields in %s" % msg.headers
        return "RECIEVED %s" % (", ".join(parts),)

    def _ignore(self, msg):
        """
        Tests if the message should be ignored based on self.reply_own setting and weather it's from your own
        node.

        :param msg: kombu.transport.base.Message instance.
        :return: Boolean
        """
        # If not ignoring don't bother testing message, just return false.
        if not self.ignore_own:
            return False
        if self.ignore_own and msg.headers.get('from', None) == DPNMQ['NODE']:
            return True
        return False