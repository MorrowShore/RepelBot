<!--
RepelBot - Discord Moderation Bot
Created by Morrow Shore
https://morrowshore.com
License: AGPLv3
-->

# RepelBot - Discord Moderation Bot

A high-performance Discord moderation bot designed for efficient message management and user moderation with auto-repel capabilities.

Repel command can be used to deal with cross-channel spam, and can be safely given to select non-moderators. 

## Features

### Manual Moderation
- **`/repel` command**: Timeout users and delete their recent messages
- Configurable message count (default: 100 messages)
- Configurable timeout duration (default: 120 minutes)
- Efficient parallel message deletion

### Auto-Repel System
- **Automatic spam detection**: Detects users spamming across multiple channels
- **Smart threshold**: Triggers when user posts in 3+ channels within 30 seconds
- **Automatic actions**: 120-minute timeout + deletion of 50 recent messages
- **Self-cleaning**: Automatically removes old activity data

### Performance Optimizations
- **Message caching**: 500 messages per channel cache for rapid access
- **Rate limit protection**: Batched operations with strategic delays
- **Parallel processing**: Concurrent channel searches and message deletions
- **Efficient API usage**: Minimizes Discord API calls

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/MorrowShore/RepelBot/tree/main
   cd webdevbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   Create a `.env` file with:
   ```env
   DISCORD_BOT_TOKEN=your_bot_token_here
   DISCORD_SERVER_ID=your_server_id_here
   DEFAULT_LOG_CHANNEL_ID=your_log_channel_id_here
   ```

## Bot Permissions Required

- **Manage Messages**: For message deletion
- **Moderate Members**: For user timeouts  
- **Read Message History**: For message searching
- **Send Messages**: For command responses

## Usage

### Manual Moderation
```
/repel user:@username messagecount:50 timeoutminutes:60
```

### Auto-Repel Triggers
The bot automatically detects and acts on:
- Users posting in 3+ different channels within 30 seconds
- Spam patterns across multiple channels

## Technical Details

### Architecture
- **Python 3.8+** with discord.py
- **Message Cache**: 500 messages/channel using `deque`
- **Activity Tracking**: Real-time user activity monitoring
- **Rate Limit Handling**: Batched operations with delays

### Performance Features
- **Parallel channel processing**: 5 channels per batch
- **Batched message fetching**: 10 messages per batch  
- **Bulk message deletion**: 100 messages per bulk operation
- **Smart retry logic**: Automatic rate limit recovery

## File Structure
```
RepelBot/
├── repel.py               # Main bot implementation
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
└── README.md              # This file
```

## Support

For issues or feature requests, please contact us on Discord: https://discord.gg/2sbnwze753

## License

AGPLv3
https://www.gnu.org/licenses/agpl-3.0.en.html

