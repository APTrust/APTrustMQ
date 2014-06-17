"""
    Yeah, well, that's just, like, your opinion, man.
    
            - The Dude

"""

import re

from dpnmq.message_schema import MessageSchema, And, Or, RequiredOnly
from dpnmq.utils import dpn_strptime
from dpnode.settings import PROTOCOL_LIST

ack_nak_name_regex = '^registry|replication.*?(cancel|create|created|reply)$'

utc_datetime_regex = '^\d{4}-\d{2}-\d{2}\D\d{2}:\d{2}:\d{2}.{1,6}$'

# little util lambda to update and return a dictionary
# it modifies the first parameter in-place.
dict_merge = lambda x, y: x.update(y) or x


VALID_HEADERS = MessageSchema({
    'from'            : And(str, lambda s: len(s) > 0),
    'reply_key'       : And(str, lambda s: len(s) > 0),
    'correlation_id'  : str,
    'sequence'        : And(int, lambda i: i > -1),
    'date'            : Or(None, And(str, lambda s: re.search(utc_datetime_regex, s, re.MULTILINE))),
    'ttl'             : Or(None, And(str, lambda s: re.search(utc_datetime_regex, s, re.MULTILINE)))
})

# Basic valid body
basic_body_dict = {
    'message_name': And(str, lambda s: re.search(ack_nak_name_regex, s, re.MULTILINE)),
    'message_att' : And(str, Or('ack', 'nak'))
}

VALID_BODY = MessageSchema(basic_body_dict)

# Fixity stuff
VALID_FIXITY = {
    'fixity_algorithm'  : MessageSchema(And(str, lambda s: s == 'sha256')),
    'fixity_value'      : MessageSchema(str)
}

# Some requiredonly fields
fixity_algorithm = RequiredOnly('fixity_algorithm', with_=('message_att', 'ack'))
fixity_value = RequiredOnly('fixity_value', with_=('message_att', 'ack'))
message_error = RequiredOnly('message_error', with_=('message_att', 'nak'))

VALID_DIRECTIVES = {

    'replication-init-query'  : MessageSchema({
        'message_name'        : 'replication-init-query',
        'replication_size'    : And(int, lambda i: i > 0),
        'protocol'            : Or(PROTOCOL_LIST,*PROTOCOL_LIST),
        'dpn_object_id'       : And(str, lambda s: len(s) > 0)
    }),

    'replication-available-reply' : MessageSchema(dict_merge({ 
        'protocol' : Or(PROTOCOL_LIST, *PROTOCOL_LIST)
        }, basic_body_dict)
    ),

    'replication-location-reply'  : MessageSchema({ 
        'message_name' : 'replication-location-reply',
        'protocol'     : Or(*PROTOCOL_LIST),
        'location'     : And(str, lambda s: len(s) > 0)
    }),

    'replication-transfer-reply': MessageSchema({
        'message_name'          : 'replication-transfer-reply',
        'message_att'           : And(str, Or('ack', 'nak')),
        fixity_algorithm        : VALID_FIXITY['fixity_algorithm'],
        fixity_value            : VALID_FIXITY['fixity_value'],
        message_error           : And(str, lambda s: len(s) > 0)
    }),

    'registry-item-create'      : MessageSchema({
        'message_name'               : 'registry-item-create',
        'dpn_object_id'              : str,
        'local_id'                   : str,
        'first_node_name'            : str,
        'replicating_node_names'     : And(list, lambda s: all(type(i) == str for i in s)),
        'version_number'             : int,
        'previous_version_object_id' : Or('null', str),
        'forward_version_object_id'  : Or('null', str),
        'first_version_object_id'    : str,
        'fixity_algorithm'           : VALID_FIXITY['fixity_algorithm'],
        'fixity_value'               : VALID_FIXITY['fixity_value'],
        'last_fixity_date'           : And(str, lambda s: re.search(utc_datetime_regex, s, re.MULTILINE)),
        'creation_date'              : And(str, lambda s: re.search(utc_datetime_regex, s, re.MULTILINE)),
        'last_modified_date'         : And(str, lambda s: re.search(utc_datetime_regex, s, re.MULTILINE)),
        'bag_size'                   : int,
        'brightening_object_id'      : And(list, lambda s: all(type(i) == str for i in s)),
        'rights_object_id'           : And(list, lambda s: all(type(i) == str for i in s)),
        'object_type'                : Or('data', 'rights', 'brightening')
    })

}


# ------------------------------
# register some signals handlers
# ------------------------------
from celery import current_app as celery
from celery.signals import after_task_publish

@after_task_publish.connect
def update_sent_state(sender=None, body=None, **kwargs):
    """
    Updates task state in order to know if task exists 
    when try to pull the state with AsyncResult
    """

    task = celery.tasks.get(sender)
    backend = task.backend if task else celery.backend
    backend.store_result(body['id'], None, "SENT")