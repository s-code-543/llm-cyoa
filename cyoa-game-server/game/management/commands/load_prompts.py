"""
Management command to load or reload all prompts from the cyoa_prompts directory.
Loads using a directory structure:
    cyoa_prompts/
        story_prompts/       -> prompt_type = filename (minus .txt)
        judge_prompts/       -> prompt_type = 'judge'
        game_ending_prompts/ -> prompt_type = 'game-ending'
"""
from django.core.management.base import BaseCommand
from game.models import Prompt
import os
import glob


class Command(BaseCommand):
    help = 'Load or update prompts from cyoa_prompts subdirectories'

    def handle(self, *args, **options):
        # Determine prompts directory path
        if os.path.exists('/story_prompts'):
            # In container volume mount, but structure might differ. 
            # Assuming volume mount is at /story_prompts and mimics project struct or just flat?
            # User instructions imply we are restructuring context. 
            # If standard docker setup maps ./cyoa_prompts:/story_prompts, then folders are inside.
            base_dir = '/story_prompts'
        else:
            # Local development
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
            base_dir = os.path.join(project_root, 'cyoa_prompts')
        
        self.stdout.write(f"Loading prompts from base: {base_dir}")
        
        if not os.path.exists(base_dir):
            self.stdout.write(self.style.ERROR(f"Base directory not found: {base_dir}"))
            return

        total_created = 0
        total_updated = 0

        # 1. Story Prompts
        stories_dir = os.path.join(base_dir, 'story_prompts')
        if os.path.exists(stories_dir):
            c, u = self.process_directory(stories_dir, default_type=None, is_system=False)
            total_created += c
            total_updated += u
        else:
            self.stdout.write(self.style.WARNING(f"Story dir missing: {stories_dir}"))

        # 2. Judge Prompts
        judge_dir = os.path.join(base_dir, 'judge_prompts')
        if os.path.exists(judge_dir):
            c, u = self.process_directory(judge_dir, default_type='judge', is_system=True)
            total_created += c
            total_updated += u
        else:
            self.stdout.write(self.style.WARNING(f"Judge dir missing: {judge_dir}"))

        # 3. Game Ending Prompts
        ending_dir = os.path.join(base_dir, 'game_ending_prompts')
        if os.path.exists(ending_dir):
            c, u = self.process_directory(ending_dir, default_type='game-ending', is_system=True)
            total_created += c
            total_updated += u
        else:
            self.stdout.write(self.style.WARNING(f"Ending dir missing: {ending_dir}"))

        self.stdout.write(self.style.SUCCESS(f"\nAll prompts processed! Created: {total_created}, Updated: {total_updated}"))

    def process_directory(self, directory, default_type=None, is_system=False):
        files = sorted(glob.glob(os.path.join(directory, '*.txt')))
        created_count = 0
        updated_count = 0

        for idx, filepath in enumerate(files):
            filename = os.path.basename(filepath)
            name_no_ext = filename.replace('.txt', '')
            
            # Read content
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to read {filename}: {e}"))
                continue

            if default_type:
                # System prompts (judge, ending)
                # Use default_type ('judge' or 'game-ending')
                # Version = index + 1 ensures unique versions if multiple files exist
                p_type = default_type
                version = idx + 1
                description = f"{name_no_ext.replace('-', ' ').title()}"
                
                # Active only if it's the latest version (highest index)
                # Or just default all to active=True and let Model logic handle exclusivity?
                # Model save() handles exclusivity for is_active=True.
                # Let's verify that. 
                # Yes, but we are doing update_or_create.
                is_active = is_system
            else:
                # Story prompts
                # Type = filename
                p_type = name_no_ext
                version = 1 # Stories are just v1 for now unless we handle story versions later
                description = name_no_ext.replace('-', ' ').replace('_', ' ').title()
                is_active = False

            prompt, created = Prompt.objects.update_or_create(
                prompt_type=p_type,
                version=version,
                defaults={
                    'description': description,
                    'prompt_text': content,
                    'is_active': is_active
                }
            )
            
            action = "Created" if created else "Updated"
            self.stdout.write(f"  ✓ {action}: [{p_type} v{version}] {description}")
            
            if created:
                created_count += 1
            else:
                updated_count += 1
        
        return created_count, updated_count
