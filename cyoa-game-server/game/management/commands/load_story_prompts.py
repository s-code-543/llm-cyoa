"""
Management command to load adventure/system prompts from cyoa_story_prompts directory.
Dynamically discovers all .txt files and loads them as separate adventure types.
"""
from django.core.management.base import BaseCommand
from game.models import Prompt
import os
import glob


class Command(BaseCommand):
    help = 'Load adventure prompts from cyoa_story_prompts directory'

    def handle(self, *args, **options):
        # Path to story prompts directory
        # In Docker, this is mounted at /story_prompts
        # Locally, look in parent directory
        if os.path.exists('/story_prompts'):
            prompts_dir = '/story_prompts'
        else:
            # Running locally - navigate from game/management/commands to project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            prompts_dir = os.path.join(os.path.dirname(project_root), 'cyoa_story_prompts')
        
        self.stdout.write(f"Loading story prompts from: {prompts_dir}")
        
        if not os.path.exists(prompts_dir):
            self.stdout.write(self.style.ERROR(f"Directory not found: {prompts_dir}"))
            return
        
        # Find all .txt files in the directory
        txt_files = glob.glob(os.path.join(prompts_dir, '*.txt'))
        
        if not txt_files:
            self.stdout.write(self.style.WARNING(f"No .txt files found in {prompts_dir}"))
            return
        
        for filepath in txt_files:
            filename = os.path.basename(filepath)
            # Use filename without extension as the adventure type
            adventure_type = filename.replace('.txt', '')
            
            # Read the prompt text
            with open(filepath, 'r', encoding='utf-8') as f:
                prompt_text = f.read().strip()
            
            # Generate description from adventure type (convert kebab-case to Title Case)
            description = adventure_type.replace('-', ' ').replace('_', ' ').title()
            
            # Check if version 1 already exists for this adventure type
            existing = Prompt.objects.filter(
                prompt_type=adventure_type,
                version=1
            ).first()
            
            if existing:
                self.stdout.write(self.style.WARNING(f"  ⚠ Already exists: {description} (v1)"))
                continue
            
            # Create version 1 of this adventure
            prompt = Prompt.objects.create(
                prompt_type=adventure_type,
                version=1,
                description=description,
                prompt_text=prompt_text,
                is_active=False  # Don't auto-activate, let admin choose
            )
            
            self.stdout.write(self.style.SUCCESS(f"  ✓ Loaded: {description} (v1) - type: {adventure_type}"))
        
        self.stdout.write(self.style.SUCCESS(f"\nStory prompts loaded successfully!"))
