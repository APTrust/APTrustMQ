from uuid import uuid4
from unittest import skip
from django.test import TestCase
from mock import patch

from kombu.message import Message
from kombu.tests.case import Mock as KombuMock

from dpnmq.tests import fixtures

from dpn_workflows.tasks import outbound

from dpn_workflows.models import IngestAction, SendFileAction, Workflow
from dpn_workflows.models import (
    VERIFY, STARTED, SUCCESS, FAILED, CANCELLED, TRANSFER, COMPLETE, RECOVERY, 
    AVAILABLE_REPLY, TRANSFER_REPLY
)

from dpn_registry.models import RegistryEntry

from dpnmq.messages import ReplicationLocationReply

from dpnode.exceptions import DPNOutboundError

class InitiateIngestTest(TestCase):

    def test_good_action(self):
        """Tests the successful request."""
        oid = uuid4()
        correlation_id = outbound.initiate_ingest(oid, 5023432)
        
        try:
            action = IngestAction.objects.get(correlation_id=correlation_id)
        except Exception as e:
            self.fail("initiate_ingest did not created a valid ingest action")    
            
        self.assertTrue(
            correlation_id, 
            "initiate_ingest did not return a correlation_id for a valid uuid"
        )
        
        self.assertEqual(
            correlation_id, 
            action.correlation_id, 
            "Correlation_id for created action did not matched returned id"
        )

    @skip("incorrect test, action returns a string. refactor")
    def test_bad_action(self):
        """Item id 0 should always fail."""
        oid = 0
        action = outbound.initiate_ingest(oid, 342342342)
        self.failIfEqual(action.correlation_id, oid)
        self.failUnlessEqual(action.object_id, oid)
        self.failUnlessEqual(action.state, FAILED)

class ChooseAndSendLocationTest(TestCase):
    fixtures = ["test_send_file_action.yaml"]
    
    def setUp(self):
        self.correlation_id = "1912a562-28a8-4995-8361-77b35f52c4eb"
        self.object_id = "1111a562-28a8-4995-8361-77b35f52c4eb"
        self.base_location = {
            'https': 'https://dpn.aptrust.org/outbound/',
            'rsync': 'dpn@dpn.aptrust.org:/outbound/',
        }
        self.file_extension = "tar"
        
    def test_choose_and_send_location(self):
        try:
            with self.settings(
                DPN_BASE_LOCATION=self.base_location,
                DPN_BAGS_FILE_EXT=self.file_extension
            ):
                 outbound.choose_and_send_location(self.correlation_id)
        except Exception as e:
            self.fail("Raised error for correct flow")
        
        action = SendFileAction.objects.get(pk=1)
        location = '{0}{1}.{2}'.format(
            self.base_location['rsync'],
            self.object_id,
            self.file_extension
        )
        
        self.assertTrue(
            action.chosen_to_transfer,
            "Action is not marked as chosen to transfer"
        )
    
        self.assertEqual(
            action.location, 
            location,
            "Action location differs from expected"
        )
        
        self.assertEqual(
            action.step, 
            TRANSFER,
            "Action step differs from expected"
        )
        
class SendTransferStatusTest(TestCase):
    fixtures = ["test_send_file_action.yaml"]
    
    def setUp(self):
        self.req = Message(
            KombuMock(), 
            fixtures.REP_LOCATION_REPLY.copy(),
            headers=fixtures.make_headers()
        )
        self.action = SendFileAction.objects.all()[0]
        
    def test_send_transfer_status(self):
        try:
            outbound.send_transfer_status(self.req, self.action)
        except:
            self.fail("Raised error for correct flow")
     
class BroadcastItemCreationTest(TestCase):
    fixtures = ["test_registry_entry.yaml", "test_node.yaml"]
    
    def setUp(self):
        self.entry = RegistryEntry.objects.all()[0]
        
    def test_broadcast_item_creation(self):
        try:
            outbound.broadcast_item_creation(self.entry)
        except:
            self.fail("Raised error for correct flow")

class VerifyFixityAndReplyTest(TestCase):
    fixtures = ["test_verify_fixity_and_reply.yaml"]
    
    def setUp(self):
        self.req = Message(KombuMock(), 
            fixtures.REP_TRANSFER_REPLY_ACK.copy(),
            headers=fixtures.make_headers())
        self.fixity_value = (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )
        self.bad_fixity_value = "000111ccc"
        self.ingest_dir_out= "dummy_dir"
    
    @patch("dpn_workflows.tasks.outbound.create_registry_entry")    
    @patch("os.path.isfile")
    @patch("dpn_workflows.tasks.outbound.generate_fixity")
    def _test_verify_fixity_and_reply_ack(self, 
        fixity_value, 
        generate_fixity, 
        isfile,
        create_registry_entry
    ):
        generate_fixity.return_value = fixity_value
        isfile.return_value = True
        create_registry_entry.return_value = True 
        try:
             with self.settings(DPN_INGEST_DIR_OUT=self.ingest_dir_out):
                 outbound.verify_fixity_and_reply(self.req)
        except Exception as e:
            self.fail("Raised error for correct flow")
    
    def test_verify_fixity_and_reply_ack(self):
        self._test_verify_fixity_and_reply_ack(self.fixity_value)
        action = SendFileAction.objects.all()[0]
        
        self.assertEqual(
            action.step, 
            COMPLETE,
            "Action step differs from expected"
        )
        
        self.assertEqual(
            action.state, 
            SUCCESS,
            "Action status differs from expected"
        )
     
    def test_verify_fixity_and_reply_nak(self):
        self._test_verify_fixity_and_reply_ack(self.bad_fixity_value)
        action = SendFileAction.objects.all()[0]
        
        self.assertEqual(
            action.step, 
            VERIFY,
            "Action step differs from expected"
        )
        
        self.assertEqual(
            action.state, 
            FAILED,
            "Action status differs from expected"
        )
           
        self.assertEqual(
            action.note, 
            "Wrong fixity value of transferred bag. Sending nak verification reply",
            "Action status differs from expected"
        )
           
class RespondToRecoveryQuery(TestCase):
    # RecoveryInitQuery
    fixtures = [
        "test_node.yaml", 
        "test_workflow.yaml", 
        "test_registry_entry.yaml"
    ]
    
    def setUp(self):
        self.headers = fixtures.make_headers()
        self.body = fixtures.REC_INIT_QUERY.copy()
        self.correlation_id = self.headers["correlation_id"]
        self.object_id = self.body["dpn_object_id"]
        self.node = self.headers["from"]
        self.reply_key = self.headers["reply_key"]
    
    @patch("os.path.isfile")
    @patch("dpn_workflows.tasks.outbound._validate_sequence")
    def _test_respond_to_recovery_query(self, req, state, validate, is_file):
        is_file.return_value = True
        with self.settings(
            DPN_XFER_OPTIONS = ['https', 'rsync'],
            DPN_BAGS_FILE_EXT = "tar",
            DPN_REPLICATION_ROOT = "test"
        ):
            try:
                outbound.respond_to_recovery_query(req)
            except:
                self.fail("Raised error for correct flow")
            
            expected_action = Workflow(
                correlation_id = self.correlation_id,
                dpn_object_id = self.object_id,
                node = self.node,
                action = RECOVERY,
                step = AVAILABLE_REPLY,
                reply_key = self.reply_key,
                note = None,
                state = state
            )
                
            actual_action = Workflow.objects.filter(state = state)[0]
            
            return different_workflow(expected_action, actual_action)
    
    def _test_respond_to_recovery_query_bad_header(
        self, 
        header_field_name, 
        header_field_value,
        workflow_field_name, 
        expected_value
    ):
        headers = self.headers.copy()
        headers[header_field_name] = header_field_value
        bad_req = Message(KombuMock(), self.body, headers = headers)
        
        dif_actions = self._test_respond_to_recovery_query(bad_req, FAILED)
           
        self.assertEqual(
            dif_actions,
            "{0} is not equal, expected: {1}, actual: {2}".format(
                workflow_field_name,
                expected_value,
                header_field_value
            ),
            "Failed validating the field: {0}".format(header_field_name)
        )
         
    def _test_respond_to_recovery_query_bad_body(
        self, 
        body_field_name, 
        body_field_value,
        workflow_field_name, 
        expected_value,
        expected_error
    ):
        body = self.body.copy()
        body[body_field_name] = body_field_value
        bad_req = Message(KombuMock(), body, headers = self.headers)
        
        dif_actions = self._test_respond_to_recovery_query(bad_req, FAILED)
           
        self.assertEqual(
            dif_actions,
            "{0} is not equal, expected: {1}, actual: {2}".format(
                workflow_field_name,
                expected_value,
                expected_error
            ),
            "Failed validating the field: {0}".format(body_field_name)
        )
         
    def test_respond_to_recovery_query_good(self):
        good_req = Message(KombuMock(), self.body, headers = self.headers)
        dif_actions = self._test_respond_to_recovery_query(good_req, SUCCESS)
           
        self.assertFalse(dif_actions, "Field Validation Failed")
    
    def test_respond_to_recovery_query_bad_node(self):
        self._test_respond_to_recovery_query_bad_header(
            "from", 
            "bad_node",
            "node", 
            self.node
        )
     
    def test_respond_to_recovery_query_bad_protocol(self):
        self._test_respond_to_recovery_query_bad_body(
            "protocol", 
            "ftp",
            "note", 
            None,
            "The protocol is not supported"
        )
            
class RespondToRecoveryTransfer(TestCase):
    # RecoveryInitQuery
    fixtures = ["test_workflow_available_reply.yaml"]
    
    def setUp(self):
        self.headers = fixtures.make_headers()
        self.body = fixtures.REC_TRANSFER_REQUEST.copy()
        self.correlation_id = self.headers["correlation_id"]
        self.object_id = "some-uuid-that-actually-looks-like-a-uuid"
        self.node = self.headers["from"]
        self.reply_key = self.headers["reply_key"]
    
    @patch("shutil.copy2")
    @patch("os.path.join")
    @patch("os.path.isfile")
    @patch("dpn_workflows.tasks.outbound._validate_sequence")
    def _test_respond_to_recovery_transfer(
        self, 
        req, 
        state, 
        validate, 
        is_file,
        os_path_join,
        shutil
    ):
        is_file.return_value = True
        os_path_join.return_value = "test/directory"
        with self.settings(
            DPN_XFER_OPTIONS = ['https', 'rsync'],
            DPN_BAGS_FILE_EXT = "tar",
            DPN_REPLICATION_ROOT = "test",
            DPN_RECOVER_LOCATION = {
                'https': 'https://dpn.aptrust.org/recovery/',
                'rsync': 'dpn@dpn.aptrust.org:/recovery/'
            }
        ):
            outbound.respond_to_recovery_transfer(req)
            
            expected_action = Workflow(
                correlation_id = self.correlation_id,
                dpn_object_id = self.object_id,
                node = self.node,
                action = RECOVERY,
                step = TRANSFER_REPLY,
                reply_key = "",
                note = None,
                state = state
            )
                
            actual_action = Workflow.objects.filter(state = state)[0]
            
            return different_workflow(expected_action, actual_action)
    
    def test_respond_to_recovery_transfer_bad_protocol(self):
        body = self.body.copy()
        body["protocol"] = "ftp"
        bad_req = Message(KombuMock(), body, headers = self.headers)
        
        self.assertRaises(
            DPNOutboundError, 
            self._test_respond_to_recovery_transfer, 
            bad_req, 
            FAILED
        )
          
    def test_respond_to_recovery_transfer_good(self):
        good_req = Message(KombuMock(), self.body, headers = self.headers)
        dif = False
        try:
            dif = self._test_respond_to_recovery_transfer(good_req, SUCCESS)
        except:
            self.fail("Raised error for correct flow")
            
        self.assertFalse(dif, "Field Validation Failed")
        
class ChooseNodeAndRecover(TestCase):
    # Fixtures:
    #     Workflow
    #
    # Mock:
    #     random.choice
    #
    # Settings:
    #     DPN_DEFAULT_XFER_PROTOCOL
    #     DPN_NODE_NAME
    fixtures = ["test_workflow_available_reply.yaml"]
    
    def setUp(self):
        self.correlation_id = "testid"
        self.dpn_object_id = "some-uuid-that-actually-looks-like-a-uuid"
        
    
    @patch("random.choice")
    def test_choose_node_and_recover(self, random_choice):
        send_action = Workflow.objects.get(pk=1)
        selected_action = Workflow.objects.get(pk=2)
        random_choice.return_value = selected_action
        
        with self.settings(
            DPN_DEFAULT_XFER_PROTOCOL = 'https',
            DPN_NODE_NAME = "testfrom",
        ):
            try:
                outbound.choose_node_and_recover(
                    self.correlation_id,
                    self.dpn_object_id,
                    send_action
                )
            except:
                self.fail("Raised error for correct flow")
    
    
           
def different_workflow(expected, actual):
    attr_list = [
        "correlation_id",
        "dpn_object_id",
        "node",
        "action",
        "step",
        "reply_key",
        "note",
        "state"
    ]
    for attr in attr_list:
        expected_attr = getattr(expected, attr)
        actual_attr = getattr(actual, attr)
        if expected_attr != actual_attr:
            return "{0} is not equal, expected: {1}, actual: {2}".format(
                attr,
                expected_attr,
                actual_attr
            )
                  