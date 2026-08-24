from django.shortcuts import render


def about_view(request):
    context = {
        'SITE_LONG_NAME': 'SKALA Online Judge',
    }
    return render(request, 'about/about.html', context)
