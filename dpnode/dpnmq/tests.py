"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""
from datetime import datetime

from django.test import TestCase

from dpnmq.messages import DPNMessage, DPNMessageError, ReplicationInitQuery
from dpnmq.messages import ReplicationAvailableReply, ReplicationLocationReply
from dpnmq.messages import ReplicationLocationCancel, ReplicationTransferReply
from dpnmq.messages import ReplicationVerificationReply
from dpnmq.util import is_string, dpn_strftime
from dpnode.settings import DPNMQ

class TestIsString(TestCase):

    def test_is_string(self):
        succeed = ['test', '%s' % 10, u'another test']
        for item in succeed:
            self.assertTrue(is_string(item))

        fail = [10, None, ""]
        for item in fail:
            self.assertFalse(is_string(item))

# class TestDPNStftime(TestCase):
#     pass

# class TestDPNStptime(TestCase):
#     pass

good_headers = {
    'from': 'testfrom',
    'reply_key': 'testkey',
    'correlation_id': 'testid',
    'sequence': 10,
    'date':  'mydate',
    'ttl':  566,
    }

class TestDPNMessage(TestCase):

    def setUp(self):
        self.msg = DPNMessage()

    def test_set_headers(self):
        exp = {
            'from': 'testfrom',
            'reply_key': 'testkey',
            'correlation_id': 'testid',
            'sequence': 10,
            'date':  'mydate',
            'ttl':  566,
        }
        self.msg.set_headers(**exp)
        for key, value in exp.iteritems():
            self.failUnlessEqual(self.msg.headers[key], value)

    def test_set_body(self):
        # Fail First
        self.assertRaises(TypeError, self.msg.set_body, "test")

        exp = {
            "message_name": "testname",
            "message_att": "nak"
        }
        self.msg.set_body(**exp)
        for key, value in exp.iteritems():
            self.failUnlessEqual(self.msg.body[key], value)

    def test_validate_headers(self):
        self.msg.set_headers(**good_headers)
        self.failUnlessEqual(None, self.msg.validate_headers())
        
        string_tests = {
            'from': "",
            'reply_key': 15,
            'correlation_id': "",
            'date': datetime.now()
        }
        for key, value in string_tests.iteritems():
            fail_headers = good_headers.copy()
            fail_headers[key] = value
            self.msg.set_headers(**fail_headers)
            self.assertRaises(DPNMessageError, self.msg.validate_headers)

        int_tests = {
            'sequence': '10',
            'ttl': '3600',
        }
        for key, value in int_tests.iteritems():
            fail_headers = good_headers.copy()
            fail_headers[key] = value
            self.msg.set_headers(**fail_headers)
            self.assertRaises(DPNMessageError, self.msg.validate_headers)

        # Fails by default with nothing set yet.
        self.msg.set_headers()
        self.assertRaises(DPNMessageError, self.msg.validate_headers)

class TestReplicationInitQuery(TestCase):

    def setUp(self):
        self.msg = ReplicationInitQuery()
        headers = {
            'correlation_id': 'andfs-ssdfbs-asdfs',
            'sequence': 1,
            'date': dpn_strftime(datetime.now()),
        }
        self.msg.set_headers(headers)

    def test_set_body(self):
        good_body = {
            'message_name': 'replication-init-query',
            'replication_size': 4502,
            'protocol': ['https', 'rsync'],
        }
        self.msg.set_body(**good_body)
        self.assertTrue(self.msg.validate_body() == None)

        bad_body = {
            'message_name': "this is not it",
            'replication_size': "3432",
            'protocol': 'https',
        }
        for key, value in bad_body.iteritems():
            fail_body = good_body.copy()
            fail_body[key] = value
            self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

class TestReplicationAvailableReply(TestCase):

    def setUp(self):
        self.msg = ReplicationAvailableReply()
        self.msg.set_headers(**good_headers)

    def test_set_body(self):
        # Establish a pass first.
        good_body_ack = {
            'message_name': 'replication-available-reply',
            'message_att': 'ack',
            'protocol': 'https'
        }
        self.msg.set_body(**good_body_ack)
        self.assertTrue(self.msg.validate_body() == None)

        good_body_nak = {
            'message_name': 'replication-available-reply',
            'message_att': 'nak',
        }
        self.msg.set_body(**good_body_nak)
        self.assertTrue(self.msg.validate_body() == None)

        bad_body_ack = {
            'message_name': 'blah',
            'message_att': 'nack',
            'protocol': 'http'
        }
        for key, value in bad_body_ack.iteritems():
            fail_body = good_body_ack.copy()
            fail_body[key] = value
            self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

        bad_body_nak = {
            'message_att': 'ack',
            'protocol': 'https'
        }
        self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

class TestReplicationLocationReply(TestCase):

    def setUp(self):
        self.msg = ReplicationLocationReply()
        self.msg.set_headers(**good_headers)

    def test_set_body(self):
        good_body = {
            'message_name': 'replication-location-reply',
            'protocol': 'https',
            'location': "https://location.com/",
        }
        self.msg.set_body(**good_body)
        self.assertTrue(self.msg.validate_body() == None)

        bad_body = {
            'message_name': 'notright',
            'protocol': 'http',
            'location': 23423,
        }
        for key, value in bad_body.iteritems():
            fail_body = good_body.copy()
            fail_body[key] = value
            self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

class TestReplicationLocationCancel(TestCase):

    def setUp(self):
        self.msg = ReplicationLocationCancel()
        self.msg.set_headers(**good_headers)

    def test_set_body(self):
        good_body = {
            'message_name': 'replication-location-cancel',
            'message_att': 'nak',
        }
        self.msg.set_body(**good_body)
        self.assertTrue(self.msg.validate_body() == None)

        bad_body = {
            'message_name': 'notright',
            'message_att': 'ack'
        }
        for key, value in bad_body.iteritems():
            fail_body = good_body.copy()
            fail_body[key] = value
            self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

class TestReplicationTransferReply(TestCase):

    def setUp(self):
        self.msg = ReplicationTransferReply()
        self.msg.set_headers(**good_headers)

    def test_set_body(self):
        good_body1 = {
            'message_name': 'replication-transfer-reply',
            'message_att': "ack",
            'fixity_algorithm':  'sha256',
            'fixity_value': "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        }
        try:
            self.msg.set_body(**good_body1)
        except DPNMessageError as err:
            self.fail(err.message)

        good_body2 = {
            'message_name': 'replication-transfer-reply',
            'message_att': "nak",
            'message_error': "This is my error."
        }
        try:
            self.msg.set_body(**good_body2)
        except DPNMessageError as err:
            self.fail(err.message)

        bad_body1 = {
            'message_name': "fail",
            'message_att':  'nak',
            'fixity_algorithm': "",
            'fixity_value': ""
        }
        for key, value in bad_body1.iteritems():
            fail_body = good_body1.copy()
            fail_body[key] = value
            self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

        bad_body2 = good_body2.copy()
        bad_body2['message_att'] = 'ack'
        self.assertRaises(DPNMessageError, self.msg.set_body, **bad_body2)

class TestReplicationVerificationReplyi(TestCase):

    def setUp(self):
        self.msg = ReplicationVerificationReply()
        self.msg.set_headers(**good_headers)

    def test_set_body(self):
        good_body = {
            'message_name': 'replication-verify-reply',
        }
        for value in ['ack', 'nak', 'retry']:
            try:
                good_body["message_att"] = value
                self.msg.set_body(**good_body)
            except DPNMessageError as err:
                self.fail(err.message)

        bad_body = {
            'message_name': 'fail', 
            'message_att': 'false',
        }
        for key, value in bad_body.iteritems():
            fail_body = good_body.copy()
            fail_body[key] = value
            self.assertRaises(DPNMessageError, self.msg.set_body, **fail_body)

