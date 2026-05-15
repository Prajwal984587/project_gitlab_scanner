// Wait for DOM to be fully loaded
$(document).ready(function() {
    console.log("Document ready - Initializing scanner");

    // Handle form submission
    $('#scanForm').on('submit', function(e) {
        e.preventDefault();
        console.log("Form submitted");

        // Get form values
        const inputType = $('input[name="input_type"]:checked').val();
        const inputName = $('#inputName').val().trim();
        const gitlabToken = $('#gitlabToken').val().trim();

        console.log("Input Type:", inputType);
        console.log("Input Name:", inputName);

        // Validate input
        if (!inputName) {
            showNotification('Please enter a username or group name', 'error');
            return;
        }

        // Prepare data for API
        const requestData = {
            input_type: inputType,
            input_name: inputName,
            gitlab_token: gitlabToken || null
        };

        // Show loading indicator
        $('#loadingIndicator').show();
        $('#scanBtn').prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Scanning...');

        // Make API call
        $.ajax({
            url: '/scan/start/',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(requestData),
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            success: function(response) {
                console.log("Scan successful:", response);
                if (response.success) {
                    showNotification('Scan completed successfully!', 'success');
                    // Redirect to results page
                    window.location.href = '/results/' + response.scan_id + '/';
                } else {
                    showNotification('Scan failed: ' + (response.error || 'Unknown error'), 'error');
                }
            },
            error: function(xhr, status, error) {
                console.error("Scan error:", xhr, status, error);
                let errorMsg = 'Failed to start scan. ';
                if (xhr.responseJSON && xhr.responseJSON.error) {
                    errorMsg += xhr.responseJSON.error;
                } else {
                    errorMsg += 'Please check the username and try again.';
                }
                showNotification(errorMsg, 'error');
            },
            complete: function() {
                $('#loadingIndicator').hide();
                $('#scanBtn').prop('disabled', false).html('<i class="fas fa-rocket"></i> Start Scan');
            }
        });
    });

    // Handle export buttons
    $('#exportPdfBtn').on('click', function() {
        const scanId = $(this).data('scan-id');
        if (scanId) {
            window.location.href = '/export/pdf/' + scanId + '/';
        }
    });

    $('#exportJsonBtn').on('click', function() {
        const scanId = $(this).data('scan-id');
        if (scanId) {
            window.location.href = '/export/json/' + scanId + '/';
        }
    });
});

// Helper function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Helper function to show notifications
function showNotification(message, type) {
    // Create notification element
    const notification = $('<div class="alert alert-' + (type === 'error' ? 'danger' : 'success') + ' alert-dismissible fade show" role="alert">' +
        message +
        '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>' +
        '</div>');

    // Add to page
    $('.container').first().prepend(notification);

    // Auto-hide after 5 seconds
    setTimeout(function() {
        notification.alert('close');
    }, 5000);
}

// Function to display results in modal (if needed)
function displayResultsInModal(results, scanId) {
    const summary = results.summary;
    let html = '<div class="row mb-3">';
    html += '<div class="col-md-4"><div class="card text-center"><div class="card-body"><h5>Total Repositories</h5><h3>' + summary.total_repos + '</h3></div></div></div>';
    html += '<div class="col-md-4"><div class="card text-center bg-danger text-white"><div class="card-body"><h5>High Risk</h5><h3>' + summary.high + '</h3></div></div></div>';
    html += '<div class="col-md-4"><div class="card text-center bg-warning"><div class="card-body"><h5>Medium Risk</h5><h3>' + summary.medium + '</h3></div></div></div>';
    html += '</div>';

    if (summary.total_repos > 0) {
        html += '<h5>Top Issues Found:</h5><ul class="list-group">';
        for (let i = 0; i < Math.min(5, results.results.length); i++) {
            const repo = results.results[i];
            html += '<li class="list-group-item"><strong>' + repo.name + '</strong><br>';
            for (let j = 0; j < Math.min(2, repo.issues.length); j++) {
                html += '<span class="badge bg-' + (repo.issues[j].severity === 'High' ? 'danger' : (repo.issues[j].severity === 'Medium' ? 'warning' : 'info')) + ' me-1">' + repo.issues[j].severity + '</span> ';
                html += repo.issues[j].description + '<br>';
            }
            html += '</li>';
        }
        html += '</ul>';
    } else {
        html += '<div class="alert alert-success">No issues found! All repositories look clean.</div>';
    }

    $('#resultsBody').html(html);
    $('#viewDetailsBtn').attr('href', '/results/' + scanId + '/');
    $('#resultsModal').modal('show');
}