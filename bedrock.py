from openai import OpenAI

client = OpenAI(
    base_url="https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1", 
    # Use your massive Bearer token key here
    api_key="" 
)

try:
    response = client.chat.completions.create(
        # This is the correct Bedrock ID for the newest Claude 3.5 Sonnet
        model="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        messages=[{"role": "user", "content": "Hello! Is this working?"}]
    )
    print("Success! Claude says:")
    print(response.choices[0].message.content)

except Exception as e:
    print(f"Error: {e}")