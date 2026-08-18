from django.shortcuts import render
from judge.models.patch_note import PatchNote

def about_view(request):
    # 게시된 패치 노트들을 가져옵니다
    patch_notes = PatchNote.objects.filter(is_published=True)
    
    context = {
        'SITE_LONG_NAME': 'DMOJ - Online Judge',
        'patch_notes': patch_notes
    }
    return render(request, 'about/about.html', context)
