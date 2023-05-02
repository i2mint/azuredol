# import wave
# import os
# import uuid

# import pytest
# from config2py.s_configparser import ConfigStore
# from py2store import QuickBinaryStore

# from azuredol.base import AzureBlobStore

# tests_dir = os.path.dirname(os.path.realpath(__file__))

# input_store = ConfigStore(os.path.join(tests_dir, 'input.ini'))
# file_store = QuickBinaryStore(os.path.join(tests_dir, 'files'))

# Azurestore = AzureBlobStore(
#     container_name=os.environ['AZURE_CONTAINER_NAME'],
#     connection_string=os.environ['AZURE_CONNECTION_STRING'],
# )
# channel = int(input_store['Values']['channel'])
# samplewidth = int(input_store['Values']['bit_depth'])
# samplerate = int(input_store['Values']['sample_rate'])


# @pytest.fixture(scope='session')
# def blob_name():
#     ##generate blob name
#     return str(uuid.uuid1())


# def test_create_blob_add_audio_data(blob_name):

#     file_path = './' + blob_name + '.wav'
#     waveFile = wave.open(file_path, 'wb')
#     waveFile.setnchannels(channel)
#     waveFile.setsampwidth(samplewidth)
#     waveFile.setframerate(samplerate)
#     waveFile.writeframes(b''.join(''))
#     waveFile.close()
#     data = open(file_path, 'rb').read()
#     os.remove(file_path)

#     try:
#         Azurestore[blob_name] = data
#     except:
#         assert False

#     file_data = Azurestore[blob_name]
#     assert len(file_data) > 0


# def test_append_audio_data(blob_name):

#     file_data = Azurestore[blob_name]
#     len_data = len(file_data)

#     try:
#         Azurestore.append(blob_name, file_store[input_store['Files']['audio_file1']])
#     except:
#         assert False

#     updated_file_data = Azurestore[blob_name]
#     assert len(updated_file_data) > len_data


# def test_append_data_not_existing_blob(blob_name):

#     try:
#         Azurestore.append(
#             blob_name + 'abc', file_store[input_store['Files']['audio_file1']]
#         )
#         assert False
#     except:
#         assert True


# def test_get_blob_data(blob_name):
#     try:
#         file_data = Azurestore[blob_name]
#     except:
#         assert False

#     assert len(file_data) > 0


# def test_get_blob_data_not_existing(blob_name):
#     try:
#         file_data = Azurestore[blob_name + 'abc']
#         assert False
#     except:
#         assert True


# def test_delete_blob(blob_name):
#     try:
#         del Azurestore[blob_name]
#     except:
#         assert False

#     try:
#         file_data = Azurestore[blob_name]
#         assert False
#     except:
#         assert True
