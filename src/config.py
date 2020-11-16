# Global constant variables (Azure Storage account/Batch details)

# import "config.py" in "batch_python_experiment.py"

# Update the Batch and Storage account credential strings below with the values
# unique to your accounts. These are used when constructing connection strings
# for the Batch and Storage client objects.


_BATCH_ACCOUNT_NAME = ''  # Your batch account name
# Your batch account key
_BATCH_ACCOUNT_KEY = ''
# Your batch account URL
_BATCH_ACCOUNT_URL = ''
_STORAGE_ACCOUNT_NAME = ''  # Your storage account name
# Your storage account key
_STORAGE_ACCOUNT_KEY = ''

_POOL_ID = 'BatchExperimentPool'
_DEDICATED_POOL_NODE_COUNT = 0
_LOW_PRIORITY_POOL_NODE_COUNT = 2
_POOL_VM_SIZE = 'STANDARD_A1_v2'
_JOB_ID = 'BatchExperimentJob'
_STANDARD_OUT_FILE_NAME = 'stdout.txt'  # Standard Output file
_ERROR_OUT_FILE_NAME = 'stderr.txt'  # Error Output file
_JOB_INPUT_PATH = 'inputFiles'
_JOB_SCRIPT_PATH = 'sourceFiles'
_TASK_ENTRY_SCRIPT = _JOB_SCRIPT_PATH + '/job.py'
