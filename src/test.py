import json
import logging
import uuid
import contextvars

import seqlog

# Define a context variable for the flow ID
flow_id_var = contextvars.ContextVar('flow_id', default=None)

class ContextFilter(logging.Filter):
    def filter(self, record):
        record.flow_id = flow_id_var.get()
        return True

seqlog.configure_from_file('./config/seqlog.yml')
logger = logging.getLogger(__name__)

context_filter = ContextFilter()
logger.addFilter(context_filter)

def set_flow_id(flow_id):
    flow_id_var.set(flow_id)

flow_id = str(uuid.uuid4())  # Generate a unique ID for the flow
print("flow_id:", flow_id)
set_flow_id(flow_id)

logger.info("Hello, World!")

# test log exception:
try:
    1 / 0
except Exception as e:
    logger.error(e, exc_info=True)

logger.warning("The weather forecast is %s", "Overcast, 24°C")
# logger_provider.shutdown()
