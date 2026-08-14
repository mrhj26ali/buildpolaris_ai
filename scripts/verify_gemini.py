import sys
sys.path.insert(0, "src")
import google.generativeai as genai
from buildpolaris_ai.platform.config import get_settings

settings = get_settings()
key = settings.model_provider.gemini_api_key
if not key:
    print("ERROR: MODEL_PROVIDER__GEMINI_API_KEY is empty in .env"); sys.exit(1)
secret = key.get_secret_value()
print(f"Key prefix: {secret[:6]}... (len {len(secret)})")
if not secret.startswith("AIza"):
    print("WARNING: Gemini keys normally start with 'AIza'. This may be an OAuth token, not an API key.")
genai.configure(api_key=secret)
try:
    models = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
    print(f"\nKey WORKS. {len(models)} models available:")
    for m in models[:12]:
        print(" ", m)
except Exception as e:
    print(f"\nKey FAILED: {e}"); sys.exit(1)
