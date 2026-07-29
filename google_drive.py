import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate_google_drive():
    # Service account JSON se credentials load karo
    creds_json = os.environ.get('SERVICE_ACCOUNT_JSON')
    if creds_json:
        # Environment variable se load
        creds_info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
    else:
        # File se load (local testing ke liye)
        with open('service-account-key.json', 'r') as f:
            creds_info = json.load(f)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
    
    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_path, folder_id=None):
    service = authenticate_google_drive()
    file_name = os.path.basename(file_path)
    
    file_metadata = {'name': file_name}
    if folder_id:
        file_metadata['parents'] = [folder_id]
    
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    return file.get('id'), file.get('webViewLink')

def list_drive_files(folder_id=None):
    service = authenticate_google_drive()
    query = ""
    if folder_id:
        query = f"'{folder_id}' in parents"
    
    results = service.files().list(
        q=query,
        pageSize=20,
        fields="files(id, name, mimeType, size)"
    ).execute()
    return results.get('files', [])

def search_drive_files(query_text, folder_id=None):
    service = authenticate_google_drive()
    query = f"name contains '{query_text}'"
    if folder_id:
        query += f" and '{folder_id}' in parents"
    
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get('files', [])

def delete_drive_file(file_id):
    service = authenticate_google_drive()
    service.files().delete(fileId=file_id).execute()
    return True

def rename_drive_file(file_id, new_name):
    service = authenticate_google_drive()
    file_metadata = {'name': new_name}
    file = service.files().update(
        fileId=file_id,
        body=file_metadata,
        fields='id, name'
    ).execute()
    return file.get('name')

def create_folder(folder_name):
    service = authenticate_google_drive()
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')

def get_or_create_user_folder(user_id):
    service = authenticate_google_drive()
    
    query = f"name = 'user_{user_id}' and mimeType = 'application/vnd.google-apps.folder'"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        return create_folder(f"user_{user_id}")
