from django.db import models
from django.utils import timezone


class ScanHistory(models.Model):
    input_type = models.CharField(max_length=10, choices=[('user', 'User'), ('group', 'Group')])
    input_name = models.CharField(max_length=255)
    scan_time = models.DateTimeField(default=timezone.now)
    total_repos = models.IntegerField()
    high_risk_count = models.IntegerField(default=0)
    medium_risk_count = models.IntegerField(default=0)
    low_risk_count = models.IntegerField(default=0)
    results_json = models.JSONField()

    class Meta:
        ordering = ['-scan_time']

    def __str__(self):
        return f"{self.input_type}: {self.input_name} - {self.scan_time}"


class RepositoryScan(models.Model):
    scan_history = models.ForeignKey(ScanHistory, on_delete=models.CASCADE, related_name='repositories')
    repo_name = models.CharField(max_length=255)
    repo_url = models.URLField()
    issues_found = models.JSONField()

    def __str__(self):
        return self.repo_name