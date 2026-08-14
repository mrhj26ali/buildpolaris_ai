import asyncio
from google import genai
from buildpolaris_ai.platform.config import get_settings

async def main():
    settings = get_settings()
    client = genai.Client(api_key=settings.model_provider.gemini_api_key.get_secret_value())
    print('Available models supporting generateContent:')
    async for m in await client.aio.models.list():
        # Check if generateContent is in supported actions
        if hasattr(m, 'supported_actions') and 'generateContent' in str(m.supported_actions):
            print(m.name)

if __name__ == '__main__':
    asyncio.run(main())
