"""
Utility functions for loading prompts and text files.
"""
import os


def load_prompt_file(filename):
    """
    Load a text file from the game/prompts directory.
    
    Args:
        filename: Name of the file to load (e.g., 'judge_prompt.txt')
    
    Returns:
        String contents of the file, stripped of leading/trailing whitespace
    """
    # Look in the same directory as this file
    base_dir = os.path.dirname(__file__)
    file_path = os.path.join(base_dir, filename)
    
    with open(file_path, 'r') as f:
        return f.read().strip()
