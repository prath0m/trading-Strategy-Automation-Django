// Custom JavaScript for Stock Data Fetcher Application

$(document).ready(function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add fade-in animation to cards
    $('.card').addClass('fade-in');

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        $('.alert').fadeOut('slow');
    }, 5000);

    // Enhanced form validation
    $('form').on('submit', function(e) {
        var form = $(this);
        var isValid = true;

        // Check required fields
        form.find('input[required], select[required]').each(function() {
            if (!$(this).val()) {
                $(this).addClass('is-invalid');
                isValid = false;
            } else {
                $(this).removeClass('is-invalid').addClass('is-valid');
            }
        });

        // Date validation for data fetch form
        if (form.attr('id') === 'data-fetch-form') {
            var fromDate = new Date($('#id_from_date').val());
            var toDate = new Date($('#id_to_date').val());
            var interval = $('#id_interval').val();

            if (fromDate > toDate) {
                showAlert('error', 'From date must be before To date');
                isValid = false;
            }

            if (interval === 'minute') {
                var diffTime = Math.abs(toDate - fromDate);
                var diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                if (diffDays > 2000) {  // Only block truly excessive requests (5+ years)
                    showAlert('warning', 'Date range is too large for minute data. Maximum recommended range is 5 years.');
                    isValid = false;
                }
                // All other ranges are handled automatically by chunked fetching
            }
        }

        if (!isValid) {
            e.preventDefault();
            form.find('.is-invalid').first().focus();
        }
    });

    // Real-time search functionality
    var searchTimeout;
    $('#search-input').on('input', function() {
        clearTimeout(searchTimeout);
        var query = $(this).val();
        
        searchTimeout = setTimeout(function() {
            if (query.length >= 2 || query.length === 0) {
                performSearch(query);
            }
        }, 300);
    });

    // Symbol selection enhancement
    $('#symbol-select').on('change', function() {
        var selectedOption = $(this).find('option:selected');
        var symbolName = selectedOption.text().split(' - ')[1];
        
        if (symbolName) {
            showToast('info', 'Selected: ' + symbolName);
        }
    });

    // Data interval change handler
    $('#id_interval').on('change', function() {
        var interval = $(this).val();
        var helpText = '';
        
        switch(interval) {
            case 'minute':
                helpText = 'Minute-wise data provides detailed intraday analysis (max 60 days)';
                break;
            case 'day':
                helpText = 'Daily data suitable for longer-term analysis';
                break;
            case '3minute':
                helpText = '3-minute intervals for medium-frequency analysis';
                break;
            case '5minute':
                helpText = '5-minute intervals for technical analysis';
                break;
        }
        
        if (helpText) {
            showToast('info', helpText);
        }
    });

    // Auto-refresh for processing requests
    if (window.location.pathname.includes('/data/')) {
        checkForProcessingRequests();
    }

    // Smooth scrolling for anchor links
    $('a[href^="#"]').on('click', function(e) {
        e.preventDefault();
        var target = $(this.getAttribute('href'));
        if (target.length) {
            $('html, body').animate({
                scrollTop: target.offset().top - 100
            }, 500);
        }
    });

    // Loading button states
    $('.btn[type="submit"]').on('click', function() {
        var btn = $(this);
        var originalText = btn.html();
        
        btn.prop('disabled', true);
        btn.html('<i class="fas fa-spinner fa-spin me-1"></i>Processing...');
        
        setTimeout(function() {
            if (btn.prop('disabled')) {
                btn.prop('disabled', false);
                btn.html(originalText);
            }
        }, 30000); // Reset after 30 seconds if still disabled
    });
});

// Utility Functions
function showAlert(type, message) {
    var alertClass = 'alert-info';
    var icon = 'fa-info-circle';
    
    switch(type) {
        case 'success':
            alertClass = 'alert-success';
            icon = 'fa-check-circle';
            break;
        case 'error':
            alertClass = 'alert-danger';
            icon = 'fa-exclamation-circle';
            break;
        case 'warning':
            alertClass = 'alert-warning';
            icon = 'fa-exclamation-triangle';
            break;
    }
    
    var alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            <i class="fas ${icon} me-2"></i>${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    $('.container').first().prepend(alertHtml);
    
    // Auto-hide after 5 seconds
    setTimeout(function() {
        $('.alert').first().fadeOut('slow');
    }, 5000);
}

function showToast(type, message) {
    // Create toast notification
    var toastClass = 'bg-info';
    
    switch(type) {
        case 'success':
            toastClass = 'bg-success';
            break;
        case 'error':
            toastClass = 'bg-danger';
            break;
        case 'warning':
            toastClass = 'bg-warning';
            break;
    }
    
    var toastHtml = `
        <div class="toast ${toastClass} text-white" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 1050;">
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    $('body').append(toastHtml);
    var toast = new bootstrap.Toast($('.toast').last());
    toast.show();
    
    // Remove toast element after it hides
    $('.toast').last().on('hidden.bs.toast', function() {
        $(this).remove();
    });
}

function performSearch(query) {
    // This would typically make an AJAX request to filter results
    // For now, we'll use client-side filtering if the data is already loaded
    
    if (query === '') {
        $('.table tbody tr').show();
        return;
    }
    
    $('.table tbody tr').each(function() {
        var row = $(this);
        var text = row.text().toLowerCase();
        
        if (text.includes(query.toLowerCase())) {
            row.show();
        } else {
            row.hide();
        }
    });
}

function checkForProcessingRequests() {
    // Check if there are any processing requests and auto-refresh
    if ($('.badge.bg-warning').length > 0) {
        setTimeout(function() {
            location.reload();
        }, 30000); // Refresh every 30 seconds
    }
}

function confirmDelete(requestId, message) {
    if (confirm(message || 'Are you sure you want to delete this item?')) {
        // Submit delete form or make AJAX request
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/delete/' + requestId + '/';
        
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        var csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = csrfToken;
        
        form.appendChild(csrfInput);
        document.body.appendChild(form);
        form.submit();
    }
}

function downloadData(requestId) {
    // Create download link and trigger download
    var link = document.createElement('a');
    link.href = '/download/' + requestId + '/';
    link.download = '';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast('success', 'Download started');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showToast('success', 'Copied to clipboard');
    }).catch(function() {
        showToast('error', 'Failed to copy to clipboard');
    });
}

// API Status Checker
function checkApiStatus() {
    $.ajax({
        url: '/api/status/',
        method: 'GET',
        timeout: 5000,
        success: function(response) {
            updateApiStatus('connected');
        },
        error: function() {
            updateApiStatus('disconnected');
        }
    });
}

function updateApiStatus(status) {
    var statusElement = $('#api-status');
    if (statusElement.length) {
        if (status === 'connected') {
            statusElement.html('<span class="badge bg-success">Connected</span>');
        } else {
            statusElement.html('<span class="badge bg-danger">Disconnected</span>');
        }
    }
}

// Chart functionality (if needed)
function renderChart(containerId, data, options) {
    // This would integrate with Chart.js or similar library
    // For now, it's a placeholder for future chart functionality
    console.log('Chart rendering placeholder for:', containerId, data);
}

// Data export functionality
function exportToCSV(data, filename) {
    var csv = convertToCSV(data);
    var blob = new Blob([csv], { type: 'text/csv' });
    var link = document.createElement('a');
    
    link.href = window.URL.createObjectURL(blob);
    link.download = filename || 'export.csv';
    link.click();
    
    showToast('success', 'CSV export completed');
}

function convertToCSV(data) {
    if (!data || data.length === 0) return '';
    
    var keys = Object.keys(data[0]);
    var csv = keys.join(',') + '\n';
    
    data.forEach(function(row) {
        csv += keys.map(function(key) {
            return '"' + (row[key] || '').toString().replace(/"/g, '""') + '"';
        }).join(',') + '\n';
    });
    
    return csv;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check API status if on relevant pages
    if (window.location.pathname.includes('/form/') || window.location.pathname.includes('/settings/')) {
        setTimeout(checkApiStatus, 1000);
    }
});
