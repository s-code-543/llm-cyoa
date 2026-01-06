"""
Admin views for CYOA prompt management and statistics.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
from .models import Prompt, AuditLog
import markdown2


def login_view(request):
    """
    Custom login view to avoid Django's default template rendering issues.
    """
    if request.user.is_authenticated:
        return redirect('/admin/dashboard/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            auth_login(request, user)
            next_url = request.GET.get('next', '/admin/dashboard/')
            return redirect(next_url)
        else:
            return render(request, 'cyoa_admin/login.html', {'error': True})
    
    return render(request, 'cyoa_admin/login.html')


@login_required
def dashboard(request):
    """
    Main dashboard showing overview statistics.
    """
    # Get statistics
    total_requests = AuditLog.objects.count()
    total_corrections = AuditLog.objects.filter(was_modified=True).count()
    correction_rate = (total_corrections / total_requests * 100) if total_requests > 0 else 0
    
    # Get active prompts
    active_prompts = Prompt.objects.filter(is_active=True)
    
    # Recent corrections
    recent_corrections = AuditLog.objects.filter(was_modified=True)[:10]
    
    context = {
        'total_requests': total_requests,
        'total_corrections': total_corrections,
        'correction_rate': f'{correction_rate:.1f}',
        'active_prompts': active_prompts,
        'recent_corrections': recent_corrections,
    }
    return render(request, 'cyoa_admin/dashboard.html', context)


@login_required
def audit_log(request):
    """
    View audit log of all requests and corrections.
    """
    # Filters
    show_modified_only = request.GET.get('modified_only') == 'true'
    
    logs = AuditLog.objects.all()
    if show_modified_only:
        logs = logs.filter(was_modified=True)
    
    # Pagination
    logs = logs[:100]  # Simple limit for now
    
    context = {
        'logs': logs,
        'show_modified_only': show_modified_only,
    }
    return render(request, 'cyoa_admin/audit_log.html', context)


@login_required
def audit_detail(request, log_id):
    """
    View detailed comparison of original vs refined output.
    """
    log = get_object_or_404(AuditLog, pk=log_id)
    
    context = {
        'log': log,
    }
    return render(request, 'cyoa_admin/audit_detail.html', context)


@login_required
def prompt_list(request):
    """
    List all prompts grouped by type.
    """
    prompt_types = Prompt.PROMPT_TYPES
    prompts_by_type = {}
    
    for type_code, type_name in prompt_types:
        prompts_by_type[type_name] = Prompt.objects.filter(prompt_type=type_code)
    
    context = {
        'prompts_by_type': prompts_by_type,
    }
    return render(request, 'cyoa_admin/prompt_list.html', context)


@login_required
def prompt_editor(request, prompt_id=None):
    """
    Edit or create a new prompt.
    """
    prompt = None
    if prompt_id:
        prompt = get_object_or_404(Prompt, pk=prompt_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save':
            # Update existing prompt
            if prompt:
                prompt.description = request.POST.get('description', '')
                prompt.prompt_text = request.POST.get('prompt_text', '')
                prompt.save()
                messages.success(request, f'Saved {prompt}')
                return redirect('admin:prompt_editor', prompt_id=prompt.id)
        
        elif action == 'save_new_version':
            # Create new version
            if prompt:
                max_version = Prompt.objects.filter(
                    prompt_type=prompt.prompt_type
                ).order_by('-version').first().version
                
                new_prompt = Prompt.objects.create(
                    prompt_type=prompt.prompt_type,
                    version=max_version + 1,
                    description=request.POST.get('description', ''),
                    prompt_text=request.POST.get('prompt_text', ''),
                    is_active=False
                )
                messages.success(request, f'Created new version: {new_prompt}')
                return redirect('admin:prompt_editor', prompt_id=new_prompt.id)
        
        elif action == 'create':
            # Create brand new prompt
            prompt_type = request.POST.get('prompt_type')
            
            # Find next version number
            max_version = Prompt.objects.filter(
                prompt_type=prompt_type
            ).order_by('-version').first()
            next_version = (max_version.version + 1) if max_version else 1
            
            new_prompt = Prompt.objects.create(
                prompt_type=prompt_type,
                version=next_version,
                description=request.POST.get('description', ''),
                prompt_text=request.POST.get('prompt_text', ''),
                is_active=False
            )
            messages.success(request, f'Created {new_prompt}')
            return redirect('admin:prompt_editor', prompt_id=new_prompt.id)
        
        elif action == 'set_active':
            if prompt:
                prompt.is_active = True
                prompt.save()
                messages.success(request, f'Set {prompt} as active')
                return redirect('admin:prompt_editor', prompt_id=prompt.id)
    
    # Get all versions of the same type for version selector
    versions = []
    if prompt:
        versions = Prompt.objects.filter(prompt_type=prompt.prompt_type)
    
    context = {
        'prompt': prompt,
        'versions': versions,
        'prompt_types': Prompt.PROMPT_TYPES,
    }
    return render(request, 'cyoa_admin/prompt_editor.html', context)


@login_required
@require_http_methods(["POST"])
def preview_markdown(request):
    """
    API endpoint to preview markdown.
    """
    text = request.POST.get('text', '')
    html = markdown2.markdown(text, extras=['fenced-code-blocks', 'tables'])
    return JsonResponse({'html': html})
