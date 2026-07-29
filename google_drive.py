import os
import json
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate_google_drive():
    creds = None
    
    # Check if token.pickle exists
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, create from environment or file
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Try to load from environment variable
            creds_json = os.environ.get('GOOGLE_CREDS_JSON')
            if creds_json:
                # Save credentials to file
                with open('credentials.json', 'w') as f:
                    f.write(creds_json)
            
            # Load from file
            if os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                # For Render - use no browser mode
                creds = flow.run_local_server(port=0, open_browser=False)
            else:
                raise Exception("credentials.json not found. Please set GOOGLE_CREDS_JSON environment variable.")
        
        # Save credentials for next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
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
