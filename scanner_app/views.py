from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.paginator import Paginator
import json
import requests
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO

from .scanner import GitLabScanner
from .models import ScanHistory, RepositoryScan


def index(request):
    """Home page view"""
    recent_scans = ScanHistory.objects.all()[:5]
    return render(request, 'scanner_app/index.html', {'recent_scans': recent_scans})


@csrf_exempt
@require_http_methods(["POST"])
def start_scan(request):
    """Start a new scan"""
    try:
        # Parse JSON data from request body
        data = json.loads(request.body.decode('utf-8'))
        input_type = data.get('input_type', 'user')
        input_name = data.get('input_name', '').strip()
        gitlab_token = data.get('gitlab_token', None)

        # Validate input
        if not input_name:
            return JsonResponse({'error': 'Please provide a username or group name'}, status=400)

        # Validate input name format (no special characters)
        if not input_name.replace('-', '').replace('_', '').isalnum():
            return JsonResponse(
                {'error': 'Invalid username/group name format. Use only letters, numbers, hyphens, and underscores.'},
                status=400)

        # Initialize scanner
        scanner = GitLabScanner(token=gitlab_token if gitlab_token else None)

        # Perform scan with try-except for specific errors
        try:
            if input_type == 'user':
                results = scanner.scan_user_repos(input_name)
            else:
                results = scanner.scan_group_repos(input_name)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return JsonResponse({
                    'error': f"{input_type.title()} '{input_name}' not found. Please check the name and try again."
                }, status=404)
            elif e.response.status_code == 403:
                return JsonResponse({
                    'error': "Access forbidden. The resource may be private or you need authentication."
                }, status=403)
            else:
                return JsonResponse({
                    'error': f"API error: {str(e)}"
                }, status=e.response.status_code)
        except requests.exceptions.ConnectionError:
            return JsonResponse({
                'error': "Connection error. Please check your internet connection and try again."
            }, status=503)
        except requests.exceptions.Timeout:
            return JsonResponse({
                'error': "Request timeout. The server took too long to respond."
            }, status=504)
        except Exception as e:
            return JsonResponse({
                'error': f"Scan failed: {str(e)}"
            }, status=500)

        # Check if any repositories found
        if not results:
            return JsonResponse({
                'warning': f"No public repositories found for {input_type} '{input_name}'",
                'results': [],
                'summary': {
                    'total_repos': 0,
                    'high': 0,
                    'medium': 0,
                    'low': 0
                }
            }, status=200)

        # Calculate summary
        high_count = sum(1 for r in results for i in r['issues'] if i['severity'] in ['High', 'Critical'])
        medium_count = sum(1 for r in results for i in r['issues'] if i['severity'] == 'Medium')
        low_count = sum(1 for r in results for i in r['issues'] if i['severity'] == 'Low')

        # Save to database
        scan_history = ScanHistory.objects.create(
            input_type=input_type,
            input_name=input_name,
            total_repos=len(results),
            high_risk_count=high_count,
            medium_risk_count=medium_count,
            low_risk_count=low_count,
            results_json=results
        )

        # Save individual repository scans
        for repo in results:
            RepositoryScan.objects.create(
                scan_history=scan_history,
                repo_name=repo['name'],
                repo_url=repo['web_url'],
                issues_found=repo['issues']
            )

        return JsonResponse({
            'success': True,
            'scan_id': scan_history.id,
            'results': results,
            'summary': {
                'total_repos': len(results),
                'high': high_count,
                'medium': medium_count,
                'low': low_count
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)


def results(request, scan_id):
    """Display scan results"""
    scan = get_object_or_404(ScanHistory, id=scan_id)
    repositories = scan.repositories.all()

    # Calculate counts for each repository
    for repo in repositories:
        high_count = 0
        medium_count = 0
        low_count = 0

        for issue in repo.issues_found:
            severity = issue.get('severity', 'Low')
            if severity in ['High', 'Critical']:
                high_count += 1
            elif severity == 'Medium':
                medium_count += 1
            else:
                low_count += 1

        repo.high_count = high_count
        repo.medium_count = medium_count
        repo.low_count = low_count

    # Pagination
    paginator = Paginator(repositories, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'scanner_app/results.html', {
        'scan': scan,
        'page_obj': page_obj,
        'repositories': page_obj
    })

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_scan(request, scan_id):
    """Delete a scan from history"""
    try:
        scan = get_object_or_404(ScanHistory, id=scan_id)
        scan.delete()
        return JsonResponse({'success': True, 'message': 'Scan deleted successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def export_pdf(request, scan_id):
    """Export scan results as PDF with proper table alignment"""
    scan = get_object_or_404(ScanHistory, id=scan_id)

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=50, rightMargin=50,
                            topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=1  # Center alignment
    )

    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=20,
        spaceBefore=20
    )

    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        leading=14
    )

    # Title
    story.append(Paragraph("GitLab Security Scan Report", title_style))
    story.append(Spacer(1, 12))

    # Scan Information Section
    story.append(Paragraph("Scan Information", heading_style))

    info_data = [
        ['Scan Type:', scan.input_type.title()],
        ['Target:', scan.input_name],
        ['Scan Time:', scan.scan_time.strftime('%Y-%m-%d %H:%M:%S')],
        ['Total Repositories:', str(scan.total_repos)],
    ]

    info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#7f8c8d')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    # Risk Summary Section
    story.append(Paragraph("Risk Summary", heading_style))

    summary_data = [
        ['Risk Level', 'Count', 'Severity'],
        ['High Risk', str(scan.high_risk_count), 'Critical security issues'],
        ['Medium Risk', str(scan.medium_risk_count), 'Security misconfigurations'],
        ['Low Risk', str(scan.low_risk_count), 'Best practice violations'],
    ]

    summary_table = Table(summary_data, colWidths=[2 * inch, 1.5 * inch, 3.5 * inch])
    summary_table.setStyle(TableStyle([
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

        # Row styling
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8c291')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f6e58d')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#c7ecee')),

        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#c0392b')),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#d35400')),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#2980b9')),

        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),

        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),

        # Borders
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#2c3e50')),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 30))

    # Detailed Findings Section
    story.append(Paragraph("Detailed Findings", heading_style))

    # Prepare data for findings table
    findings_data = [['Repository', 'Issue Category', 'Description', 'Severity']]

    for repo in scan.repositories.all():
        for issue in repo.issues_found:
            # Truncate description if too long
            description = issue['description']
            if len(description) > 200:
                description = description[:197] + '...'

            # Create Paragraph objects for text wrapping
            repo_name_para = Paragraph(repo.repo_name, normal_style)
            category_para = Paragraph(issue['category'], normal_style)
            description_para = Paragraph(description, normal_style)

            # Severity with color
            severity_text = issue['severity']
            if severity_text == 'Critical' or severity_text == 'High':
                severity_para = Paragraph(f'<font color="#c0392b"><b>{severity_text}</b></font>', normal_style)
            elif severity_text == 'Medium':
                severity_para = Paragraph(f'<font color="#d35400"><b>{severity_text}</b></font>', normal_style)
            else:
                severity_para = Paragraph(f'<font color="#2980b9"><b>{severity_text}</b></font>', normal_style)

            findings_data.append([repo_name_para, category_para, description_para, severity_para])

    # Create table with proper column widths
    col_widths = [1.5 * inch, 1.2 * inch, 3.5 * inch, 0.8 * inch]

    findings_table = Table(findings_data, colWidths=col_widths, repeatRows=1)

    # Style the table
    table_style = TableStyle([
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

        # Row styling
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffffff')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('VALIGN', (0, 1), (-1, -1), 'TOP'),

        # Padding
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),

        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f8f9fa')]),

        # Borders
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#2c3e50')),

        # Alignment for severity column
        ('ALIGN', (3, 1), (3, -1), 'CENTER'),
        ('VALIGN', (3, 1), (3, -1), 'MIDDLE'),
    ])

    findings_table.setStyle(table_style)
    story.append(findings_table)

    # Add footer with page numbers
    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.HexColor('#7f8c8d'))
        page_num = canvas.getPageNumber()
        canvas.drawCentredString(4.25 * inch, 0.5 * inch, f"Page {page_num}")
        canvas.drawCentredString(4.25 * inch, 10.5 * inch, "GitLab Security Scanner Report")
        canvas.restoreState()

    # Build PDF
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response[
        'Content-Disposition'] = f'attachment; filename="gitlab_scan_report_{scan.id}_{scan.scan_time.strftime("%Y%m%d_%H%M%S")}.pdf"'
    return response


def export_json(request, scan_id):
    """Export scan results as JSON"""
    scan = get_object_or_404(ScanHistory, id=scan_id)

    data = {
        'scan_id': scan.id,
        'input_type': scan.input_type,
        'input_name': scan.input_name,
        'scan_time': scan.scan_time.isoformat(),
        'total_repos': scan.total_repos,
        'summary': {
            'high': scan.high_risk_count,
            'medium': scan.medium_risk_count,
            'low': scan.low_risk_count
        },
        'repositories': [
            {
                'name': repo.repo_name,
                'url': repo.repo_url,
                'issues': repo.issues_found
            }
            for repo in scan.repositories.all()
        ]
    }

    response = JsonResponse(data, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="scan_report_{scan.id}.json"'
    return response


def history(request):
    """View scan history"""
    scans = ScanHistory.objects.all()
    paginator = Paginator(scans, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'scanner_app/history.html', {'page_obj': page_obj})