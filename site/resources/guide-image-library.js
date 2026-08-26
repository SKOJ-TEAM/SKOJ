(function () {
    'use strict';

    function escapeMarkdown(value) {
        return value.replace(/[\\\[\]]/g, '\\$&');
    }

    function insertAtCursor(editor, text) {
        var position = editor.getCursorPosition();
        editor.session.insert(position, text);
        editor.focus();
    }

    function buildLibrary(editor) {
        var overlay = document.createElement('div');
        overlay.className = 'guide-image-library-overlay';
        overlay.innerHTML = '<div class="guide-image-library-dialog">' +
            '<div class="guide-image-library-header"><strong>사진 자료 선택</strong>' +
            '<button type="button" class="guide-image-library-close" aria-label="닫기">×</button></div>' +
            '<input class="guide-image-library-search" type="search" placeholder="자료명 검색">' +
            '<div class="guide-image-library-grid">불러오는 중...</div>' +
            '<div class="guide-image-library-footer"><a href="/admin/judge/guideimage/add/" target="_blank">새 사진 업로드</a></div>' +
            '</div>';
        document.body.appendChild(overlay);

        var grid = overlay.querySelector('.guide-image-library-grid');
        var search = overlay.querySelector('.guide-image-library-search');
        var timer;

        function close() { overlay.remove(); }
        function load() {
            grid.textContent = '불러오는 중...';
            fetch('/admin/judge/guideimage/library/?q=' + encodeURIComponent(search.value), {
                credentials: 'same-origin'
            }).then(function (response) {
                if (!response.ok) throw new Error('사진 자료를 불러오지 못했습니다.');
                return response.json();
            }).then(function (data) {
                grid.textContent = '';
                if (!data.images.length) {
                    grid.textContent = '등록된 사진 자료가 없습니다.';
                    return;
                }
                data.images.forEach(function (image) {
                    var button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'guide-image-library-item';
                    var img = document.createElement('img');
                    img.src = image.url;
                    img.alt = '';
                    var label = document.createElement('span');
                    label.textContent = image.title;
                    button.appendChild(img);
                    button.appendChild(label);
                    button.addEventListener('click', function () {
                        insertAtCursor(editor, '![' + escapeMarkdown(image.alt) + '](' + image.url + ')');
                        close();
                    });
                    grid.appendChild(button);
                });
            }).catch(function (error) { grid.textContent = error.message; });
        }

        overlay.querySelector('.guide-image-library-close').addEventListener('click', close);
        overlay.addEventListener('click', function (event) { if (event.target === overlay) close(); });
        search.addEventListener('input', function () {
            clearTimeout(timer);
            timer = setTimeout(load, 250);
        });
        load();
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof ace === 'undefined') return;
        document.querySelectorAll('.main-martor').forEach(function (container) {
            var fieldName = container.getAttribute('data-field-name');
            var editorElement = document.getElementById('martor-' + fieldName);
            var toolbar = container.querySelector('.martor-toolbar .buttons');
            if (!editorElement || !toolbar || toolbar.querySelector('.guide-image-library-button')) return;

            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'guide-image-library-button';
            button.textContent = '사진 자료실';
            button.addEventListener('click', function () { buildLibrary(ace.edit(editorElement)); });
            toolbar.appendChild(button);
        });
    });
})();
