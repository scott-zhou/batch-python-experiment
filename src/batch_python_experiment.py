import datetime
import io
import os
import sys
import time
import config
from typing import List, Generator

try:
    input = raw_input
except NameError:
    pass

import azure.storage.blob as azureblob
import azure.batch.batch_service_client as batch
import azure.batch.batch_auth as batchauth
import azure.batch.models as batchmodels

sys.path.append('.')
sys.path.append('..')

# Update the Batch and Storage account credential strings in config.py with values
# unique to your accounts. These are used when constructing connection strings
# for the Batch and Storage client objects.


def query_yes_no(question: str, default: str = "yes") -> str:
    """
    Prompts the user for yes/no input, displaying the specified question text.

    :param question: The text of the prompt for input.
    :param default: The default if the user hits <ENTER>. Acceptable values
    are 'yes', 'no', and None.
    :return: 'yes' or 'no'
    """
    valid = {'y': 'yes', 'n': 'no'}
    if default is None:
        prompt = ' [y/n] '
    elif default == 'yes':
        prompt = ' [Y/n] '
    elif default == 'no':
        prompt = ' [y/N] '
    else:
        raise ValueError("Invalid default answer: '{}'".format(default))

    while 1:
        choice = input(question + prompt).lower()
        if default and not choice:
            return default
        try:
            return valid[choice[0]]
        except (KeyError, IndexError):
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


def print_batch_exception(
        batch_exception: batchmodels.BatchErrorException) -> None:
    """
    Prints the contents of the specified Batch exception.
    """
    print('-------------------------------------------')
    print('Exception encountered:')
    if batch_exception.error and \
            batch_exception.error.message and \
            batch_exception.error.message.value:
        print(batch_exception.error.message.value)
        if batch_exception.error.values:
            print()
            for mesg in batch_exception.error.values:
                print('{}:\t{}'.format(mesg.key, mesg.value))
    print('-------------------------------------------')


def upload_file_to_container(
        block_blob_client: azureblob.BlockBlobService,
        container_name: str,
        file_path: str,
        folder: str = None) -> batchmodels.ResourceFile:
    """
    Uploads a local file to an Azure Blob storage container.

    :param block_blob_client: A blob service client.
    :param container_name: The name of the Azure Blob storage container.
    :param file_path: The local path to the file.
    :param folder: The folder on container to store the file, default None.
    :return: A ResourceFile initialized with a SAS URL appropriate for Batch
    tasks.
    """
    if folder:
        blob_name = f"{folder}/{os.path.basename(file_path)}"
    else:
        blob_name = os.path.basename(file_path)

    print('Uploading file {} to container [{}]...'.format(file_path,
                                                          container_name))

    block_blob_client.create_blob_from_path(container_name,
                                            blob_name,
                                            file_path)

    # Obtain the SAS token for the container.
    sas_token = get_container_sas_token(block_blob_client,
                                        container_name, azureblob.BlobPermissions.READ)

    sas_url = block_blob_client.make_blob_url(container_name,
                                              blob_name,
                                              sas_token=sas_token)

    return batchmodels.ResourceFile(file_path=blob_name,
                                    http_url=sas_url)


def get_container_sas_token(
        block_blob_client: azureblob.BlockBlobService,
        container_name: str,
        blob_permissions: azureblob.BlobPermissions) -> str:
    """
    Obtains a shared access signature granting the specified permissions to the
    container.

    :param block_blob_client: A blob service client.
    :param container_name: The name of the Azure Blob storage container.
    :param blob_permissions:
    :return: A SAS token granting the specified permissions to the container.
    """
    # Obtain the SAS token for the container, setting the expiry time and
    # permissions. In this case, no start time is specified, so the shared
    # access signature becomes valid immediately. Expiration is in 2 hours.
    container_sas_token = \
        block_blob_client.generate_container_shared_access_signature(
            container_name,
            permission=blob_permissions,
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=2))

    return container_sas_token


def get_container_sas_url(
        block_blob_client: azureblob.BlockBlobService,
        container_name: str,
        blob_permissions: azureblob.BlobPermissions) -> str:
    """
    Obtains a shared access signature URL that provides write access to the
    ouput container to which the tasks will upload their output.

    :param block_blob_client: A blob service client.
    :param container_name: The name of the Azure Blob storage container.
    :param blob_permissions:
    :return: A SAS URL granting the specified permissions to the container.
    """
    # Obtain the SAS token for the container.
    sas_token = get_container_sas_token(block_blob_client,
                                        container_name, azureblob.BlobPermissions.WRITE)

    # Construct SAS URL for the container
    container_sas_url = "https://{}.blob.core.windows.net/{}?{}".format(
        config._STORAGE_ACCOUNT_NAME, container_name, sas_token)

    return container_sas_url


def create_pool(
        batch_service_client: batch.BatchServiceClient,
        pool_id: str,
        publisher: str = "Canonical",
        offer: str = "UbuntuServer",
        sku: str = "18.04-LTS") -> None:
    """
    Creates a pool of compute nodes with the specified OS settings.

    :param batch_service_client: A Batch service client.
    :param pool_id: An ID for the new pool.
    :param publisher: Marketplace image publisher
    :param offer: Marketplace image offer
    :param sku: Marketplace image sky
    """
    print('Creating pool [{}]...'.format(pool_id))

    # Create a new pool of Linux compute nodes using an Azure Virtual Machines
    # Marketplace image. For more information about creating pools of Linux
    # nodes, see:
    # https://azure.microsoft.com/documentation/articles/batch-linux-nodes/

    new_pool = batch.models.PoolAddParameter(
        id=pool_id,
        virtual_machine_configuration=batchmodels.VirtualMachineConfiguration(
            image_reference=batchmodels.ImageReference(
                publisher=publisher,
                offer=offer,
                sku=sku,
                version="latest"
            ),
            node_agent_sku_id="batch.node.ubuntu 18.04"),
        vm_size=config._POOL_VM_SIZE,
        target_dedicated_nodes=config._DEDICATED_POOL_NODE_COUNT,
        target_low_priority_nodes=config._LOW_PRIORITY_POOL_NODE_COUNT,
        start_task=batchmodels.StartTask(
            command_line="/bin/bash -c \"apt-get update && apt-get -y install python3.7 python3-pip\"",
            wait_for_success=True,
            user_identity=batchmodels.UserIdentity(
                auto_user=batchmodels.AutoUserSpecification(
                    scope=batchmodels.AutoUserScope.pool,
                    elevation_level=batchmodels.ElevationLevel.admin)),
        )
    )
    batch_service_client.pool.add(new_pool)


def create_job(
        batch_service_client: batch.BatchServiceClient,
        job_id: str,
        pool_id: str) -> None:
    """
    Creates a job with the specified ID, associated with the specified pool.

    :param batch_service_client: A Batch service client.
    :param job_id: The ID for the job.
    :param pool_id: The ID for the pool.
    """
    print('Creating job [{}]...'.format(job_id))

    job = batch.models.JobAddParameter(
        id=job_id,
        pool_info=batch.models.PoolInformation(pool_id=pool_id))

    batch_service_client.job.add(job)


def add_tasks(
        batch_service_client: batch.BatchServiceClient,
        job_id: str,
        source_files: List[batchmodels.ResourceFile],
        input_files: List[batchmodels.ResourceFile],
        output_container_sas_url: str) -> None:
    """
    Adds a task for each input file in the collection to the specified job.

    :param batch_service_client: A Batch service client.
    :param job_id: The ID of the job to which to add the tasks.
    :param source_files: A collection of source files.
    :param input_files: A collection of input files. One task will be created
     for each input file.
    :param output_container_sas_url: A SAS URL granting the specified
     permissions to the output container.
    """

    print('Adding {} tasks to job [{}]...'.format(len(input_files), job_id))

    tasks = list()
    for idx, input_file in enumerate(input_files):
        input_file_path = input_file.file_path
        output_file_path = "".join(
            (os.path.basename(input_file_path)).split('.')[:-1]) + 'output.txt'
        command = "/bin/bash -c \""\
            "python3.7 -m pip install --upgrade pip && "\
            "python3.7 -m pip install wheel && "\
            f"python3.7 -m pip install -r {config._JOB_SCRIPT_PATH}/requirements.txt && "\
            f"python3.7 {config._TASK_ENTRY_SCRIPT} {input_file_path} {output_file_path}"\
            "\""
        tasks.append(
            batch.models.TaskAddParameter(
                id='Task{}'.format(idx),
                command_line=command,
                resource_files=source_files+[input_file],
                output_files=[batchmodels.OutputFile(
                    file_pattern=output_file_path,
                    destination=batchmodels.OutputFileDestination(
                        container=batchmodels.OutputFileBlobContainerDestination(
                              container_url=output_container_sas_url)),
                    upload_options=batchmodels.OutputFileUploadOptions(
                        upload_condition=batchmodels.OutputFileUploadCondition.task_success))]
            )
        )
    batch_service_client.task.add_collection(job_id, tasks)


def wait_for_tasks_to_complete(
        batch_service_client: batch.BatchServiceClient,
        job_id: str,
        timeout: datetime.timedelta) -> None:
    """
    Returns when all tasks in the specified job reach the Completed state.

    :param batch_service_client: A Batch service client.
    :param job_id: The id of the job whose tasks should be monitored.
    :param timeout: The duration to wait for task completion. If all
     tasks in the specified job do not reach Completed state within this time
     period, an exception will be raised.
    """
    timeout_expiration = datetime.datetime.now() + timeout

    print("Monitoring all tasks for 'Completed' state, timeout in {}..."
          .format(timeout), end='')

    while datetime.datetime.now() < timeout_expiration:
        print('.', end='')
        sys.stdout.flush()
        tasks = batch_service_client.task.list(job_id)

        incomplete_tasks = [task for task in tasks if
                            task.state != batchmodels.TaskState.completed]
        if not incomplete_tasks:
            print()
            return True
        else:
            time.sleep(1)

    print()
    raise RuntimeError("ERROR: Tasks did not reach 'Completed' state within "
                       "timeout period of " + str(timeout))


def print_task_output(
        batch_service_client: batch.BatchServiceClient,
        job_id: str,
        blob_client: azureblob.BlockBlobService,
        output_container_name: str,
        encoding: str = None) -> None:
    """Prints the stdout, stderr and output files for each task in the job.

    :param batch_service_client: The batch client to use.
    :param job_id: The id of the job with task output files to print.
    :param blob_client: A blob service client.
    :param output_container_name: The name for output container
    :param encoding: The encoding of the file. The default is utf-8.
    """

    print('Printing task output...')

    tasks = batch_service_client.task.list(job_id)

    models = []

    for task in tasks:

        node_id = batch_service_client.task.get(
            job_id, task.id).node_info.node_id
        print("Task: {}".format(task.id))
        print("Node: {}".format(node_id))

        stream = batch_service_client.file.get_from_task(
            job_id, task.id, config._STANDARD_OUT_FILE_NAME)

        file_text = _read_stream_as_string(
            stream,
            encoding)
        print("Standard output:")
        print(file_text)

        stream = batch_service_client.file.get_from_task(
            job_id, task.id, config._ERROR_OUT_FILE_NAME)

        file_text = _read_stream_as_string(
            stream,
            encoding)
        print("Error output:")
        print(file_text)

        for outputfile in task.output_files:
            output = io.BytesIO()
            blob_client.get_blob_to_stream(
                output_container_name, outputfile.file_pattern, output)
            file_content = output.getvalue().decode('utf-8')
            print(f"Output file {outputfile.file_pattern}:")
            print(file_content)
            name, score, *_ = file_content.splitlines()
            score = float(score.split(": ")[1])
            models.append((score, name))
    print("\n\nEvaluation and comparision of all the models:")
    print(f"{'Model':<25}R-squared Score")
    for m in sorted(models, reverse=True):
        print(f"{m[1]:<25}{m[0]}")


def _read_stream_as_string(stream: Generator, encoding: str) -> str:
    """Read stream as string

    :param stream: input stream generator
    :param encoding: The encoding of the file. The default is utf-8.
    :return: The file content.
    """
    output = io.BytesIO()
    try:
        for data in stream:
            output.write(data)
        if encoding is None:
            encoding = 'utf-8'
        return output.getvalue().decode(encoding)
    finally:
        output.close()
    raise RuntimeError('could not write data to stream or decode bytes')


def _upload_input_files(
        blob_client: azureblob.BlockBlobService,
        container_name: str) -> List[batchmodels.ResourceFile]:
    """Upload input files to Azure Storage Account

    :param blob_client: A blob service client.
    :param container_name: The name of the Azure Blob storage container.
    :return: A collection of input files.
    """
    # Create a list of all job defination files in the inputFiles directory.
    input_file_paths = []

    for folder, _, files in os.walk(os.path.join(sys.path[0], config._JOB_INPUT_PATH)):
        for filename in files:
            if filename.endswith(".txt"):
                input_file_paths.append(os.path.abspath(
                    os.path.join(folder, filename)))

    # Upload the input files. This is the collection of files that are to be processed by the tasks.
    return [
        upload_file_to_container(
            blob_client, container_name, file_path, config._JOB_INPUT_PATH)
        for file_path in input_file_paths]


def _upload_source_files(
        blob_client: azureblob.BlockBlobService,
        container_name: str) -> List[batchmodels.ResourceFile]:
    """Upload script source files to Azure Storage Account

    :param blob_client: A blob service client.
    :param container_name: The name of the Azure Blob storage container.
    :return: A collection of script source files.
    """
    # Create a list of all Python source files
    source_code_paths = []
    for folder, _, files in os.walk(os.path.join(sys.path[0], config._JOB_SCRIPT_PATH)):
        for filename in files:
            if filename.endswith(".py") or filename == "requirements.txt":
                source_code_paths.append(os.path.abspath(
                    os.path.join(folder, filename)))

    # Upload the source files, and set the job.py as main entry
    return [
        upload_file_to_container(
            blob_client, container_name, file_path, config._JOB_SCRIPT_PATH)
        for file_path in source_code_paths
    ]


if __name__ == '__main__':

    start_time = datetime.datetime.now().replace(microsecond=0)
    print('Sample start: {}'.format(start_time))
    print()

    # Create the blob client, for use in obtaining references to
    # blob storage containers and uploading files to containers.

    blob_client = azureblob.BlockBlobService(
        account_name=config._STORAGE_ACCOUNT_NAME,
        account_key=config._STORAGE_ACCOUNT_KEY)

    # Use the blob client to create the containers in Azure Storage if they
    # don't yet exist.

    input_container_name = f'input-{int(start_time.timestamp())}'
    blob_client.create_container(input_container_name, fail_on_exist=False)
    print('Container [{}] created.'.format(input_container_name))

    output_container_name = f'output-{int(start_time.timestamp())}'
    blob_client.create_container(output_container_name, fail_on_exist=False)
    print('Container [{}] created.'.format(output_container_name))

    input_files = _upload_input_files(blob_client, input_container_name)
    config._LOW_PRIORITY_POOL_NODE_COUNT = len(
        input_files)  # Change pool size from num of input

    source_files = _upload_source_files(blob_client, input_container_name)
    if not any(
        os.path.basename(f.file_path) == config._TASK_ENTRY_SCRIPT.name for f in source_files
    ):
        raise RuntimeError("ERROR: Did not find job entry source code file")

    # Obtain a shared access signature URL that provides write access to the output
    # container to which the tasks will upload their output.
    output_container_sas_url = get_container_sas_url(
        blob_client,
        output_container_name,
        azureblob.BlobPermissions.WRITE)

    # Create a Batch service client. We'll now be interacting with the Batch
    # service in addition to Storage
    credentials = batchauth.SharedKeyCredentials(config._BATCH_ACCOUNT_NAME,
                                                 config._BATCH_ACCOUNT_KEY)

    batch_client = batch.BatchServiceClient(
        credentials,
        batch_url=config._BATCH_ACCOUNT_URL)

    batch_pool_id = f"{config._POOL_ID}_{int(start_time.timestamp())}"
    job_id = f"{config._JOB_ID}_{int(start_time.timestamp())}"
    try:
        # Create the pool that will contain the compute nodes that will execute the tasks.
        create_pool(batch_client, batch_pool_id)

        # Create the job that will run the tasks.
        create_job(batch_client, job_id, batch_pool_id)

        # Add the tasks to the job. Pass the input files and a SAS URL
        # to the storage container for output files.
        add_tasks(batch_client, job_id, source_files,
                  input_files, output_container_sas_url)

        # Pause execution until tasks reach Completed state.
        wait_for_tasks_to_complete(batch_client,
                                   job_id,
                                   datetime.timedelta(minutes=30))

        print("  Success! All tasks reached the 'Completed' state within the "
              "specified timeout period.")

        # Print the stdout, stderr, and output files for each task to the console
        print_task_output(batch_client, job_id, blob_client,
                          output_container_name)

    except batchmodels.BatchErrorException as err:
        print_batch_exception(err)
        raise

    # Print out some timing info
    end_time = datetime.datetime.now().replace(microsecond=0)
    print()
    print('Sample end: {}'.format(end_time))
    print('Elapsed time: {}'.format(end_time - start_time))
    print()

    # Delete input container in storage
    if query_yes_no('Delete input container?') == 'yes':
        print('Deleting container [{}]...'.format(input_container_name))
        blob_client.delete_container(input_container_name)

    # Clean up Batch resources (if the user so chooses).
    if query_yes_no('Delete job?') == 'yes':
        batch_client.job.delete(job_id)

    if query_yes_no('Delete pool?') == 'yes':
        batch_client.pool.delete(batch_pool_id)

    # Delete output container in storage
    if query_yes_no('Delete output container?') == 'yes':
        print('Deleting container [{}]...'.format(output_container_name))
        blob_client.delete_container(output_container_name)

    print()
    input('Press ENTER to exit...')
