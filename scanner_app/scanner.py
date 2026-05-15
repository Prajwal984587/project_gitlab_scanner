import requests
import re
from typing import List, Dict, Optional
import urllib.parse


class GitLabScanner:
    def __init__(self, base_url='https://gitlab.com/api/v4', token=None):
        self.base_url = base_url
        self.headers = {}
        if token:
            self.headers['PRIVATE-TOKEN'] = token

    def scan_user_repos(self, username: str) -> List[Dict]:
        """Scan all public repositories for a user"""
        username = username.lower().strip()
        repos = self._get_user_projects(username)
        return self._scan_repositories(repos)

    def scan_group_repos(self, group_name: str) -> List[Dict]:
        """Scan all public repositories for a group"""
        repos = self._get_group_projects(group_name)
        return self._scan_repositories(repos)

    def _get_user_projects(self, username: str) -> List[Dict]:
        """Fetch user's projects from GitLab API"""
        url = f"{self.base_url}/users/{username}/projects"
        params = {'visibility': 'public', 'per_page': 100, 'page': 1}
        all_projects = []

        while True:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 404:
                raise Exception(f"User '{username}' not found")

            response.raise_for_status()

            projects = response.json()
            if not projects:
                break

            all_projects.extend(projects)
            params['page'] += 1

        return all_projects

    def _get_group_projects(self, group_name: str) -> List[Dict]:
        """Fetch group's projects from GitLab API"""
        url = f"{self.base_url}/groups/{group_name}"
        response = requests.get(url, headers=self.headers, timeout=30)

        if response.status_code == 404:
            raise Exception(f"Group '{group_name}' not found")

        response.raise_for_status()

        group_info = response.json()
        group_id = group_info['id']

        url = f"{self.base_url}/groups/{group_id}/projects"
        params = {'visibility': 'public', 'per_page': 100, 'page': 1}
        all_projects = []

        while True:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()

            projects = response.json()
            if not projects:
                break

            all_projects.extend(projects)
            params['page'] += 1

        return all_projects

    def _scan_repositories(self, repos: List[Dict]) -> List[Dict]:
        """Scan each repository for risks"""
        results = []

        for repo in repos:
            print(f"Scanning repository: {repo['name']}")
            repo_name = repo['name']
            repo_id = repo['id']
            issues = []

            # Get all files in repository
            all_files = self._get_all_repository_files(repo_id)

            # Check for sensitive files by name
            sensitive_files = self._check_sensitive_files(all_files)
            issues.extend(sensitive_files)

            # Scan file contents for sensitive data
            sensitive_data = self._scan_files_for_sensitive_data(repo_id, all_files)
            issues.extend(sensitive_data)

            # Check for missing metadata
            missing_metadata = self._check_missing_metadata(repo)
            issues.extend(missing_metadata)

            if issues:
                results.append({
                    'name': repo_name,
                    'web_url': repo['web_url'],
                    'issues': issues
                })

        return results

    def _get_all_repository_files(self, project_id: int, path: str = '') -> List[Dict]:
        """Get all files in repository recursively"""
        url = f"{self.base_url}/projects/{project_id}/repository/tree"
        params = {'path': path, 'per_page': 100, 'recursive': 'true'}
        all_files = []

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            if response.status_code == 200:
                files = response.json()
                for file in files:
                    if file.get('type') == 'blob':
                        all_files.append(file)
        except Exception as e:
            print(f"Error fetching files: {e}")

        return all_files

    def _get_file_content(self, project_id: int, file_path: str) -> Optional[str]:
        """Get file content from repository"""
        encoded_path = urllib.parse.quote(file_path, safe='')
        url = f"{self.base_url}/projects/{project_id}/repository/files/{encoded_path}/raw"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                try:
                    return response.text
                except:
                    return None
        except:
            pass
        return None

    def _check_sensitive_files(self, files: List[Dict]) -> List[Dict]:
        """Check for sensitive files by filename"""
        sensitive_patterns = [
            (r'.*\.env$', 'Environment file found', 'High'),
            (r'.*\.pem$', 'Private key file found', 'High'),
            (r'.*id_rsa.*', 'SSH private key file found', 'High'),
            (r'.*\.key$', 'Key file found', 'High'),
            (r'.*credentials.*\.(json|yml|yaml)$', 'Credentials file found', 'High'),
            (r'.*\.sql$', 'Database file found', 'Medium'),
            (r'\.htpasswd$', 'Password file found', 'High'),
            (r'.*\.kdbx$', 'Password database found', 'High'),
        ]

        issues = []
        for file in files:
            file_path = file.get('path', '')
            for pattern, description, severity in sensitive_patterns:
                if re.match(pattern, file_path, re.IGNORECASE):
                    issues.append({
                        'category': 'Sensitive File',
                        'description': f"{description}: {file_path}",
                        'severity': severity
                    })
                    break

        return issues

    def _scan_files_for_sensitive_data(self, project_id: int, files: List[Dict]) -> List[Dict]:
        """Scan all files for any sensitive data - store clean description"""
        issues = []

        # Text file extensions to scan
        text_extensions = {'.txt', '.py', '.js', '.json', '.yml', '.yaml', '.xml', '.conf', '.cfg', '.ini',
                           '.sh', '.bash', '.md', '.env', '.properties', '.toml', '.sql', '.php', '.rb',
                           '.go', '.rs', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.html', '.css', '.ts'}

        # Track which files already have issues
        files_with_issues = set()

        for file in files:
            file_path = file.get('path', '')
            ext = '.' + file_path.split('.')[-1] if '.' in file_path else ''

            if ext in text_extensions and file_path not in files_with_issues:
                content = self._get_file_content(project_id, file_path)
                if content:
                    # Check for sensitive patterns
                    if self._contains_sensitive_data(content):
                        issues.append({
                            'category': 'Sensitive Data',
                            'description': f"Sensitive data found in file: {file_path}",
                            'severity': 'High',
                            'file': file_path
                        })
                        files_with_issues.add(file_path)

        return issues

    def _contains_sensitive_data(self, content: str) -> bool:
        """Check if content contains any sensitive data"""
        sensitive_patterns = [
            r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']([^"\'\s]{4,})["\']',
            r'(?i)(api[_-]?key|apikey|api_token)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{10,})["\']',
            r'(?i)(token|access_token|auth_token|bearer)\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{10,})["\']',
            r'(?i)(secret|secrets?)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{8,})["\']',
            r'(?i)(username|user|email)\s*[:=]\s*["\']([^"\'\s]+@[^"\'\s]+\.[^"\'\s]{2,})["\']',
            r'-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----',
            r'verify\s*=\s*False',
            r'debug\s*=\s*True',
            r'sk-[a-zA-Z0-9]{20,}',
            r'gh[pousr]_[a-zA-Z0-9]{36}',
            r'glpat-[a-zA-Z0-9\-_]{20}',
        ]

        for pattern in sensitive_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            if matches:
                # Check if it's a placeholder/demo value
                value_str = str(matches[0]) if matches else ''
                placeholder_keywords = ['example', 'test', 'demo', 'placeholder', 'changeme', 'fake', 'your-']

                if not any(keyword in value_str.lower() for keyword in placeholder_keywords):
                    return True

        return False


    def _check_missing_metadata(self, repo: Dict) -> List[Dict]:
        """Check for missing repository metadata"""
        issues = []

        if not repo.get('readme_url'):
            issues.append({
                'category': 'Missing Metadata',
                'description': 'Missing README.md file',
                'severity': 'Low'
            })

        if not repo.get('license_url'):
            issues.append({
                'category': 'Missing Metadata',
                'description': 'Missing LICENSE file',
                'severity': 'Medium'
            })

        if not repo.get('description'):
            issues.append({
                'category': 'Missing Metadata',
                'description': 'Missing repository description',
                'severity': 'Low'
            })

        return issues