(function ($) {
    'use strict';

    $(function () {
        var $select = $('#id_problems');
        var $orderInput = $('#id_problem_order');
        if (!$select.length || !$orderInput.length || $('#problem-group-order').length) {
            return;
        }

        function parseIds(value) {
            if (!value) {
                return [];
            }
            return value.split(',').map(function (id) {
                return $.trim(id);
            }).filter(Boolean);
        }

        var originalIds = new Set(parseIds($orderInput.attr('data-original-problem-ids')));
        var order = parseIds($orderInput.val());
        var draggedId = null;

        var $container = $('<div id="problem-group-order" class="module"></div>');
        var $heading = $('<h2>학습 노출 순서</h2>');
        var $help = $('<p class="help">위아래로 끌어서 배치하세요. 저장하면 1번부터 연속된 순서로 정리됩니다.</p>');
        var $table = $('<table><thead><tr><th class="order-handle-column">이동</th><th class="order-number-column">순서</th><th>문제</th><th class="order-actions-column">조작</th></tr></thead><tbody></tbody></table>');
        var $tbody = $table.find('tbody');
        $container.append($heading, $help, $table);
        $select.closest('.form-row').after($container);

        function selectedLabels() {
            var labels = {};
            $select.find('option:selected').each(function () {
                labels[String(this.value)] = $(this).text();
            });
            return labels;
        }

        function updateOrderInput() {
            order = [];
            $tbody.find('tr[data-problem-id]').each(function () {
                order.push(String($(this).attr('data-problem-id')));
            });
            $orderInput.val(order.join(','));
            $tbody.find('.problem-order-number').each(function (index) {
                $(this).text(index + 1);
            });
        }

        function moveRow(problemId, offset) {
            var $row = $tbody.find('tr[data-problem-id="' + problemId + '"]');
            if (!$row.length) {
                return;
            }
            if (offset < 0 && $row.prev().length) {
                $row.insertBefore($row.prev());
            } else if (offset > 0 && $row.next().length) {
                $row.insertAfter($row.next());
            }
            updateOrderInput();
        }

        function render() {
            var labels = selectedLabels();
            var selectedIds = Object.keys(labels);
            order = order.filter(function (id) {
                return Object.prototype.hasOwnProperty.call(labels, id);
            });
            selectedIds.forEach(function (id) {
                if (order.indexOf(id) === -1) {
                    order.push(id);
                }
            });

            $tbody.empty();
            order.forEach(function (id, index) {
                var $row = $('<tr draggable="true"></tr>').attr('data-problem-id', id);
                var $handle = $('<td class="problem-order-handle" title="끌어서 이동" aria-label="끌어서 이동">☰</td>');
                var $number = $('<td class="problem-order-number"></td>').text(index + 1);
                var $label = $('<td class="problem-order-label"></td>').text(labels[id]);
                var $actions = $('<td class="problem-order-actions"></td>');
                var $up = $('<button type="button" class="button" aria-label="위로 이동">↑</button>');
                var $down = $('<button type="button" class="button" aria-label="아래로 이동">↓</button>');
                $up.on('click', function () { moveRow(id, -1); });
                $down.on('click', function () { moveRow(id, 1); });
                $actions.append($up, $down);

                if (!originalIds.has(id)) {
                    var $cancel = $('<button type="button" class="button problem-order-cancel">추가 취소</button>');
                    $cancel.on('click', function () {
                        $select.find('option[value="' + id + '"]').prop('selected', false);
                        $select.trigger('change');
                    });
                    $actions.append($cancel);
                }

                $row.on('dragstart', function (event) {
                    draggedId = id;
                    event.originalEvent.dataTransfer.effectAllowed = 'move';
                    event.originalEvent.dataTransfer.setData('text/plain', id);
                    $row.addClass('dragging');
                });
                $row.on('dragend', function () {
                    draggedId = null;
                    $row.removeClass('dragging');
                    $tbody.find('tr').removeClass('drag-over');
                });
                $row.on('dragover', function (event) {
                    event.preventDefault();
                    if (draggedId && draggedId !== id) {
                        $row.addClass('drag-over');
                    }
                });
                $row.on('dragleave', function () {
                    $row.removeClass('drag-over');
                });
                $row.on('drop', function (event) {
                    event.preventDefault();
                    $row.removeClass('drag-over');
                    if (!draggedId || draggedId === id) {
                        return;
                    }
                    var $dragged = $tbody.find('tr[data-problem-id="' + draggedId + '"]');
                    var targetIndex = $row.index();
                    var draggedIndex = $dragged.index();
                    if (draggedIndex < targetIndex) {
                        $dragged.insertAfter($row);
                    } else {
                        $dragged.insertBefore($row);
                    }
                    updateOrderInput();
                });

                $row.append($handle, $number, $label, $actions);
                $tbody.append($row);
            });
            updateOrderInput();
        }

        $select.on('select2:unselecting', function (event) {
            var params = event.params || {};
            var data = params.data || (params.args && params.args.data) || {};
            var id = String(data.id || '');
            if (originalIds.has(id)) {
                event.preventDefault();
                window.alert('기존 문제는 다른 그룹으로 이동해야 합니다.');
            }
        });
        $select.on('change select2:select select2:unselect', render);
        $select.closest('form').on('submit', updateOrderInput);

        render();
    });
})(django.jQuery);
