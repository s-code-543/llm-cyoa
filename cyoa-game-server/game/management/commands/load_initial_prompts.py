"""
Management command to load initial judge prompt from file into database.
Run this after initial migrations to populate the database.
"""
from django.core.management.base import BaseCommand
from game.models import Prompt
from game.file_utils import load_prompt_file


class Command(BaseCommand):
    help = 'Load initial judge prompt from initial-judge-prompt.txt into database'

    def handle(self, *args, **options):
        # Check if judge prompt already exists
        existing = Prompt.objects.filter(prompt_type='judge', version=1).first()
        
        if existing:
            self.stdout.write(
                self.style.WARNING('Judge prompt v1 already exists in database')
            )
            self.stdout.write(f'  Created: {existing.created_at}')
            self.stdout.write(f'  Active: {existing.is_active}')
            self.stdout.write(f'  Description: {existing.description}')
            return
        
        try:
            # Load from file
            prompt_text = load_prompt_file('initial-judge-prompt.txt')
            
            # Create initial prompt
            prompt = Prompt.objects.create(
                prompt_type='judge',
                version=1,
                description='Initial judge prompt - validates story turns for broken game design',
                prompt_text=prompt_text,
                is_active=True
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created judge prompt v1')
            )
            self.stdout.write(f'  Length: {len(prompt_text)} chars')
            self.stdout.write(f'  Active: {prompt.is_active}')
            
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR('Could not find initial-judge-prompt.txt')
            )
            self.stdout.write(
                'Please ensure the file exists in the game/ directory'
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error loading initial prompt: {e}')
            )
