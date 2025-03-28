# Discord Toxicity Analyzer

A Discord bot that analyzes messages in a channel for toxicity using the Friendly Text Moderation API.

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the root directory with your Discord bot token:
```
DISCORD_TOKEN=your_discord_bot_token_here
```

3. Run the bot:
```bash
python bot.py
```

## Usage

1. Invite the bot to your server with appropriate permissions
2. Use the command `!analyze` in any channel to start analyzing messages
3. The bot will analyze each message and provide toxicity scores and categories

## Features

- Real-time message analysis
- Toxicity scoring
- Message categorization
- Easy to use commands 

**Toxicity Detection**
The application uses Duc Haba's Friendly_Text_Moderation API to detect toxic content in comments. This API analyzes text and provides toxicity scores across several categories:

General toxicity
Identity attacks
Insults
Obscenity
Severe toxicity
Sexual explicit content
Threats
You can adjust the "safer" value to control the sensitivity of the toxicity detection. A higher value means less strict filtering (more content will be shown).

Credits
Friendly_Text_Moderation(https://huggingface.co/spaces/duchaba/Friendly_Text_Moderation) by Duc Haba for toxicity detection
