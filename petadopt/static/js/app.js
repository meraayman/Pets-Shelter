/* Shared admin behaviour */
$(function () {
  // Sortable, searchable tables. Each table can set its default sort with data-order.
  $('.pa-datatable').each(function () {
    $(this).DataTable({
      responsive: true,
      autoWidth: false,
      pageLength: 25,
      order: $(this).data('order') || [],
      language: {
        search: '',
        searchPlaceholder: 'Search',
        lengthMenu: 'Show _MENU_',
        info: 'Showing _START_ to _END_ of _TOTAL_',
        infoEmpty: 'No records',
        infoFiltered: '(filtered from _MAX_)',
        zeroRecords: 'Nothing matches that search.',
        paginate: { previous: '‹', next: '›' }
      }
    });
  });

  // Ask before deleting anything
  $(document).on('submit', 'form[data-confirm]', function (e) {
    if (!window.confirm($(this).data('confirm'))) e.preventDefault();
  });

  // Show a chosen photo before it's uploaded
  $('input[type=file][data-preview]').on('change', function () {
    var file = this.files && this.files[0];
    var img = $(this).closest('.card-body, form').find($(this).data('preview')).first();
    if (file && img.length && file.type.indexOf('image/') === 0) {
      img.attr('src', URL.createObjectURL(file));
    }
  });

  // Success messages fade out; errors stay until the page changes
  setTimeout(function () { $('.pa-flash--ok').fadeOut('slow'); }, 5000);
});

// Confirm for individual buttons (used when one form has several actions)
$(document).on('click', '[data-confirm-click]', function (e) {
  if (!window.confirm($(this).data('confirm-click'))) e.preventDefault();
});
