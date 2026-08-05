import os

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "service_account.json"
OAUTH_CLIENT_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SHEET_FILE_ID = "1RO_8HAm2U-BlVSiAXiP1ImZEEAptpSiuwAAmgdioFuc"
TARGET_EMAIL = "mhtpnwr@gmail.com"


def get_credentials():
    # Prefer service account when available, else reuse OAuth token/client files.
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        return service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.path.exists(OAUTH_CLIENT_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise FileNotFoundError(
                "Missing both service_account.json and credentials.json. "
                "Provide one of them to authenticate."
            )

        with open(TOKEN_FILE, "w", encoding="utf-8") as token_fh:
            token_fh.write(creds.to_json())

    return creds


def grant_read_permission(file_id: str, target_email: str) -> dict:
    creds = get_credentials()
    drive_service = build("drive", "v3", credentials=creds)

    permission = {
        "type": "user",
        "role": "reader",
        "emailAddress": target_email,
    }

    return drive_service.permissions().create(
        fileId=file_id,
        body=permission,
        sendNotificationEmail=True,
    ).execute()


if __name__ == "__main__":
    response = grant_read_permission(SHEET_FILE_ID, TARGET_EMAIL)
    print("Permission granted:", response.get("id"))