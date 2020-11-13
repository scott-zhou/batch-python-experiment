import datetime
import io
import os
import sys
import time
import config

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


def query_yes_no(question, default="yes"):
    """
    Prompts the user for yes/no input, displaying the specified question text.

    :param str question: The text of the prompt for input.
    :param str default: The default if the user hits <ENTER>. Acceptable values
    are 'yes', 'no', and None.
    :rtype: str
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


def print_batch_exception(batch_exception):
    """
    Prints the contents of the specified Batch exception.

    :param batch_exception:
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


def upload_file_to_container(block_blob_client, container_name, file_path, folder=None):
    """
    Uploads a local file to an Azure Blob storage container.

    :param block_blob_client: A blob service client.
    :type block_blob_client: `azure.storage.blob.BlockBlobService`
    :param str container_name: The name of the Azure Blob storage container.
    :param str file_path: The local path to the file.
    :param str folder: The folder on container to store the file, default None.
    :rtype: `azure.batch.models.ResourceFile`
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


def get_container_sas_token(block_blob_client,
                            container_name, blob_permissions):
    """
    Obtains a shared access signature granting the specified permissions to the
    container.

    :param block_blob_client: A blob service client.
    :type block_blob_client: `azure.storage.blob.BlockBlobService`
    :param str container_name: The name of the Azure Blob storage container.
    :param BlobPermissions blob_permissions:
    :rtype: str
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


def get_container_sas_url(block_blob_client,
                          container_name, blob_permissions):
    """
    Obtains a shared access signature URL that provides write access to the
    ouput container to which the tasks will upload their output.

    :param block_blob_client: A blob service client.
    :type block_blob_client: `azure.storage.blob.BlockBlobService`
    :param str container_name: The name of the Azure Blob storage container.
    :param BlobPermissions blob_permissions:
    :rtype: str
    :return: A SAS URL granting the specified permissions to the container.
    """
    # Obtain the SAS token for the container.
    sas_token = get_container_sas_token(block_blob_client,
                                        container_name, azureblob.BlobPermissions.WRITE)

    # Construct SAS URL for the container
    container_sas_url = "https://{}.blob.core.windows.net/{}?{}".format(
        config._STORAGE_ACCOUNT_NAME, container_name, sas_token)

    return container_sas_url


def create_pool(batch_service_client, pool_id):
    """
    Creates a pool of compute nodes with the specified OS settings.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str pool_id: An ID for the new pool.
    :param str publisher: Marketplace image publisher
    :param str offer: Marketplace image offer
    :param str sku: Marketplace image sky
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
                publisher="Canonical",
                offer="UbuntuServer",
                sku="18.04-LTS",
                version="latest"
            ),
            node_agent_sku_id="batch.node.ubuntu 18.04"),
        vm_size=config._POOL_VM_SIZE,
        target_dedicated_nodes=config._DEDICATED_POOL_NODE_COUNT,
        target_low_priority_nodes=config._LOW_PRIORITY_POOL_NODE_COUNT,
        start_task=batchmodels.StartTask(
            command_line="/bin/bash -c \"apt-get update && apt-get -y install python3.7\"",
            wait_for_success=True,
            user_identity=batchmodels.UserIdentity(
                auto_user=batchmodels.AutoUserSpecification(
                    scope=batchmodels.AutoUserScope.pool,
                    elevation_level=batchmodels.ElevationLevel.admin)),
        )
    )

    batch_service_client.pool.add(new_pool)


def create_job(batch_service_client, job_id, pool_id):
    """
    Creates a job with the specified ID, associated with the specified pool.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str job_id: The ID for the job.
    :param str pool_id: The ID for the pool.
    """
    print('Creating job [{}]...'.format(job_id))

    job = batch.models.JobAddParameter(
        id=job_id,
        pool_info=batch.models.PoolInformation(pool_id=pool_id))

    batch_service_client.job.add(job)


def add_tasks(batch_service_client, job_id, job_entry, source_files, input_files, output_container_sas_url):
    """
    Adds a task for each input file in the collection to the specified job.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str job_id: The ID of the job to which to add the tasks.
    :param ResourceFile job_entry: The main entry of Python script.
    :param list source_files: A collection of source files.
    :param list input_files: A collection of input files. One task will be
     created for each input file.
    :param output_container_sas_token: A SAS token granting write access to
    the specified Azure Blob storage container.
    """

    print('Adding {} tasks to job [{}]...'.format(len(input_files), job_id))

    tasks = list()
    job_entry_path = job_entry.file_path
    for idx, input_file in enumerate(input_files):
        input_file_path = input_file.file_path
        output_file_path = "".join(
            (os.path.basename(input_file_path)).split('.')[:-1]) + 'output.txt'
        command = f"/bin/bash -c \"ls -l && python3.7 {job_entry_path} {input_file_path} {output_file_path}\""
        tasks.append(batch.models.TaskAddParameter(
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


def wait_for_tasks_to_complete(batch_service_client, job_id, timeout):
    """
    Returns when all tasks in the specified job reach the Completed state.

    :param batch_service_client: A Batch service client.
    :type batch_service_client: `azure.batch.BatchServiceClient`
    :param str job_id: The id of the job whose tasks should be monitored.
    :param timedelta timeout: The duration to wait for task completion. If all
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


def print_task_output(batch_service_client, job_id, encoding=None):
    """Prints the stdout.txt file for each task in the job.

    :param batch_client: The batch client to use.
    :type batch_client: `batchserviceclient.BatchServiceClient`
    :param str job_id: The id of the job with task output files to print.
    """

    print('Printing task output...')

    tasks = batch_service_client.task.list(job_id)

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


def _read_stream_as_string(stream, encoding):
    """Read stream as string

    :param stream: input stream generator
    :param str encoding: The encoding of the file. The default is utf-8.
    :return: The file content.
    :rtype: str
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
    output_container_name = f'output-{int(start_time.timestamp())}'
    blob_client.create_container(input_container_name, fail_on_exist=False)
    blob_client.create_container(output_container_name, fail_on_exist=False)
    print('Container [{}] created.'.format(input_container_name))
    print('Container [{}] created.'.format(output_container_name))

    # Create a list of all job defination files in the inputFiles directory.
    input_file_paths = []

    for folder, subs, files in os.walk(os.path.join(sys.path[0], 'inputFiles')):
        for filename in files:
            if filename.endswith(".txt"):
                input_file_paths.append(os.path.abspath(
                    os.path.join(folder, filename)))

    # Upload the input files. This is the collection of files that are to be processed by the tasks.
    input_files = [
        upload_file_to_container(
            blob_client, input_container_name, file_path, 'inputFiles')
        for file_path in input_file_paths]

    # Create a list of all Python source files
    source_code_paths = []
    for folder, subs, files in os.walk(os.path.join(sys.path[0], 'sourceFiles')):
        for filename in files:
            if filename.endswith(".py"):
                source_code_paths.append(os.path.abspath(
                    os.path.join(folder, filename)))

    # Upload the source files, and set the job.py as main entry
    job_main_entry = None
    source_files = []
    for file_path in source_code_paths:
        res_file = upload_file_to_container(
            blob_client, input_container_name, file_path, 'sourceFiles')
        source_files.append(res_file)
        if os.path.basename(file_path) == "job.py":
            job_main_entry = res_file
    if not job_main_entry:
        raise RuntimeError("ERROR: Die not find job entry source code file")

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
        # Create the pool that will contain the compute nodes that will execute the
        # tasks.
        create_pool(batch_client, batch_pool_id)

        # Create the job that will run the tasks.
        create_job(batch_client, job_id, batch_pool_id)

        # Add the tasks to the job. Pass the input files and a SAS URL
        # to the storage container for output files.
        add_tasks(batch_client, job_id, job_main_entry, source_files,
                  input_files, output_container_sas_url)

        # Pause execution until tasks reach Completed state.
        wait_for_tasks_to_complete(batch_client,
                                   job_id,
                                   datetime.timedelta(minutes=30))

        print("  Success! All tasks reached the 'Completed' state within the "
              "specified timeout period.")

        # Print the stdout.txt and stderr.txt files for each task to the console
        print_task_output(batch_client, job_id)

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