(function () {
    'use strict';
    document.addEventListener('DOMContentLoaded', function () {
        const form = document.getElementById('avatar-form');
        if (!form) return;
        const fileInput = document.getElementById('avatar-file');
        const crop = document.getElementById('avatar-crop');
        const canvas = document.getElementById('avatar-preview');
        const context = canvas.getContext('2d');
        const zoom = document.getElementById('avatar-zoom');
        const panX = document.getElementById('avatar-x');
        const panY = document.getElementById('avatar-y');
        const save = document.getElementById('avatar-save');
        const remove = document.getElementById('avatar-remove');
        const status = document.getElementById('avatar-status');
        let picture = null;
        let selection = 0;
        let busy = false;
        let hasAvatar = !remove.disabled;
        let pointer = null;

        function message(text, error) {
            status.textContent = text;
            status.dataset.error = error ? 'true' : 'false';
        }
        function controls() {
            fileInput.disabled = busy;
            save.disabled = busy || !picture;
            remove.disabled = busy || !hasAvatar;
            [zoom, panX, panY].forEach(function (input) { input.disabled = busy; });
            form.setAttribute('aria-busy', String(busy));
        }
        function region() {
            const size = Math.min(picture.naturalWidth, picture.naturalHeight) / Number(zoom.value);
            return {size: size, x: (picture.naturalWidth - size) * Number(panX.value) / 100,
                y: (picture.naturalHeight - size) * Number(panY.value) / 100};
        }
        function draw() {
            if (!picture) return;
            const box = region();
            context.clearRect(0, 0, canvas.width, canvas.height);
            context.drawImage(picture, box.x, box.y, box.size, box.size, 0, 0, canvas.width, canvas.height);
        }
        function clearSelection() {
            selection += 1;
            picture = null;
            pointer = null;
            crop.hidden = true;
            fileInput.value = '';
            controls();
        }
        fileInput.addEventListener('change', function () {
            const file = fileInput.files[0];
            const token = ++selection;
            picture = null;
            crop.hidden = true;
            controls();
            if (!file) { message(''); return; }
            if (file.size > 5 * 1024 * 1024) {
                clearSelection(); message('사진은 5MB 이하로 올려주세요.', true); return;
            }
            if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
                clearSelection(); message('JPG, PNG, WebP 사진만 사용할 수 있습니다.', true); return;
            }
            message('사진을 불러오는 중입니다.');
            // A data URL follows the existing image CSP; the original never leaves the browser until saving.
            const reader = new FileReader();
            function failed() {
                if (token !== selection) return;
                clearSelection(); message('사진을 읽을 수 없습니다. 다른 파일을 선택해주세요.', true);
            }
            reader.onerror = failed;
            reader.onload = function () {
                if (token !== selection) return;
                const image = new Image();
                image.onerror = failed;
                image.onload = function () {
                    if (token !== selection) return;
                    if (image.naturalWidth * image.naturalHeight > 25000000 ||
                            Math.max(image.naturalWidth, image.naturalHeight) > 10000) {
                        clearSelection(); message('사진은 2,500만 화소 이하, 가로·세로 각각 10,000px 이하로 올려주세요.', true); return;
                    }
                    picture = image;
                    zoom.value = '1'; panX.value = '50'; panY.value = '50';
                    crop.hidden = false;
                    draw(); controls(); message('사진의 위치와 확대를 조절한 뒤 사진 저장을 눌러주세요.');
                };
                image.src = reader.result;
            };
            reader.readAsDataURL(file);
        });
        [zoom, panX, panY].forEach(function (input) { input.addEventListener('input', draw); });
        canvas.addEventListener('pointerdown', function (event) {
            if (!picture || busy || !event.isPrimary) return;
            pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
            canvas.setPointerCapture(event.pointerId);
        });
        canvas.addEventListener('pointermove', function (event) {
            if (!pointer || pointer.id !== event.pointerId || !picture || busy) return;
            const box = region();
            const scale = box.size / canvas.getBoundingClientRect().width;
            function position(value, distance, available) {
                return available > 0 ? Math.max(0, Math.min(100, (value - distance * scale) / available * 100)) : 50;
            }
            panX.value = position(box.x, event.clientX - pointer.x, picture.naturalWidth - box.size);
            panY.value = position(box.y, event.clientY - pointer.y, picture.naturalHeight - box.size);
            pointer.x = event.clientX; pointer.y = event.clientY;
            draw();
        });
        ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function (event) {
            canvas.addEventListener(event, function () { pointer = null; });
        });
        async function submit(action) {
            if (busy || (action === 'upload' && !picture)) return;
            const data = new FormData();
            data.append('csrfmiddlewaretoken', form.querySelector('[name="csrfmiddlewaretoken"]').value);
            data.append('action', action);
            if (action === 'upload') {
                const box = region();
                data.append('image', fileInput.files[0]);
                data.append('crop_x', box.x); data.append('crop_y', box.y); data.append('crop_size', box.size);
            }
            busy = true; controls(); message('저장 중입니다.');
            try {
                const response = await fetch(form.action, {method: 'POST', body: data, credentials: 'same-origin'});
                if (response.redirected || response.status === 403) throw new Error('로그인 상태를 확인하고 페이지를 새로고침해주세요.');
                if (response.status === 413) throw new Error('사진은 5MB 이하로 올려주세요.');
                if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('사진을 저장하지 못했습니다. 잠시 후 다시 시도해주세요.');
                const result = await response.json();
                if (!response.ok) {
                    const errors = Object.values(result.errors || {}).flat().map(function (error) { return error.message; });
                    throw new Error(errors.join(' ') || '사진을 저장하지 못했습니다.');
                }
                document.querySelectorAll('[data-own-avatar]').forEach(function (image) { image.src = result.avatar_url; });
                hasAvatar = result.has_avatar;
                clearSelection();
                message(action === 'upload' ? '프로필 사진을 저장했습니다.' : '기본 이미지로 변경했습니다.');
            } catch (error) {
                message(error.message || '연결을 확인하고 다시 시도해주세요.', true);
            } finally {
                busy = false; controls();
            }
        }
        form.addEventListener('submit', function (event) { event.preventDefault(); submit('upload'); });
        remove.addEventListener('click', function () { submit('remove'); });
    });
})();
