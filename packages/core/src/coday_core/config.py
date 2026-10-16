# 환경 설정 로딩
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env") # env 읽기 

github_app_id = os.environ["GITHUB_APP_ID"]
github_private_key_path = Path(os.environ["GITHUB_PRIVATE_KEY_PATH"])