# CYOA Game Server - Admin Interface

## Overview

The CYOA Game Server now includes a Django-based admin interface for managing judge prompts and viewing correction statistics.

## Features

### 📊 Dashboard
- View total requests, corrections, and correction rate
- See active prompts at a glance
- Quick access to recent corrections

### 📝 Audit Log
- Complete history of all requests
- Filter to show only corrections
- Side-by-side comparison of original vs refined outputs
- Track which prompt version was used for each request

### 🎯 Prompt Management
- Create and manage multiple prompt types (judge, storyteller, etc.)
- Version control for prompts
- Edit prompts with markdown-aware text editor
- Preview markdown formatting
- Set active prompt for API calls
- Save as new version or overwrite existing

## Getting Started

### Initial Setup

1. **Run the setup script:**
   ```bash
   cd cyoa-game-server
   ./setup.sh
   ```
   
   This will:
   - Create the database
   - Run migrations
   - Prompt you to create a superuser account
   - Load the initial judge prompt into the database

2. **Start the server:**

   **Option A: Docker (Recommended)**
   ```bash
   cd ..
   docker-compose -f docker-compose.mac.yml up -d cyoa-game-server
   ```
   
   **Option B: Local Development**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

3. **Access the admin interface:**
   - URL: http://localhost:8001/admin/login/
   - Login with the superuser credentials you created

## Using the Admin Interface

### Managing Prompts

1. Navigate to **Prompts** in the top menu
2. You'll see all prompt types and their versions
3. Click **Edit** on any prompt to:
   - Modify the description
   - Edit the prompt text
   - Preview markdown formatting
   - Save changes or create a new version
   - Set as active (this version will be used for API calls)

#### Creating New Prompts

1. Click **+ New Prompt**
2. Select the prompt type
3. Enter a description
4. Write your prompt text
5. Use the formatting toolbar for basic markdown
6. Click **Create Prompt**

#### Version Management

- **Save Changes**: Updates the current version
- **Save as New Version**: Creates a new version number
- **Set as Active**: Makes this version active for API calls
- Only one version per type can be active at a time

### Viewing Statistics

1. **Dashboard**: High-level overview of system performance
2. **Audit Log**: Detailed history of all requests
   - Click "View" to see side-by-side comparison
   - Filter to show only corrections
   - See which prompt was used for each request

### Understanding Corrections

A "correction" occurs when the judge LLM modifies the storyteller's output:
- **Modified**: Judge made changes to fix game design issues
- **Unchanged**: Judge approved the output as-is

The correction rate helps you understand how often the judge needs to intervene.

## API Usage

The game API endpoints remain unchanged:
- `POST /v1/chat/completions` - Main game endpoint
- Uses the active judge prompt from the database
- Logs all corrections to the audit table

## Remote Debugging

The server runs with debugpy enabled:
1. Start the Docker container
2. In VS Code, run the "Attach to Django in Docker" debug configuration
3. Set breakpoints in your code
4. Debugger will attach on port 5678

## Database

- **Type**: SQLite
- **Location**: `/app/db/db.sqlite3` (inside container)
- **Persistence**: Mounted to Docker volume `cyoa-db`

### Models

**Prompt**
- `prompt_type`: Type of prompt (judge, storyteller, etc.)
- `version`: Version number
- `description`: User-friendly description
- `prompt_text`: The actual prompt content
- `is_active`: Whether this version is currently active

**AuditLog**
- `timestamp`: When the request was processed
- `original_text`: Storyteller's output
- `refined_text`: Final output after judge
- `was_modified`: Whether judge made changes
- `prompt_used`: Which prompt version was active

## Development Notes

### Adding New Prompt Types

Edit `game/models.py`:
```python
PROMPT_TYPES = [
    ('judge', 'Judge Prompt'),
    ('storyteller', 'Storyteller Prompt'),
    ('test', 'Test Prompt'),
    ('your_new_type', 'Your New Type'),  # Add here
]
```

Then run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

### Customizing the UI

Templates are in `game/templates/admin/`:
- `base.html` - Main layout with Tailwind CSS
- `dashboard.html` - Dashboard view
- `audit_log.html` - Audit log table
- `audit_detail.html` - Comparison view
- `prompt_list.html` - List of all prompts
- `prompt_editor.html` - Prompt editor with markdown preview

## Troubleshooting

### Database Issues
```bash
# Reset database (WARNING: Deletes all data)
docker-compose down -v
docker-compose up -d cyoa-game-server
docker exec -it cyoa-game-server ./setup.sh
```

### No Active Prompt
If the API fails with "No active judge prompt", ensure:
1. You ran `python manage.py load_initial_prompts`
2. At least one judge prompt is marked as active
3. Check the prompts page and set one as active

### Debug Mode
Set `DJANGO_DEBUG=1` in docker-compose.mac.yml to see detailed error pages.

## Security Notes

- Change `DJANGO_SECRET_KEY` in production
- Use strong passwords for superuser accounts
- The admin interface requires authentication
- API endpoints remain unauthenticated (for Open WebUI compatibility)
