"""
UserService - Business logic for user-related operations

Handles user data enrichment, team associations, and other user-related operations.
"""

import logging
from typing import Dict, List

from src.services.team_service import team_service


logger = logging.getLogger(__name__)


class UserService:
    """Service for user-related operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_user_teams(self, user_id: int) -> List[Dict]:
        """
        Get all teams associated with a user (both owned and enrolled)
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of team dictionaries with owner information (same format as teams list API)
        """
        try:
            teams_data = []
            
            # Get own-teams (teams where user is owner)
            own_teams_result = team_service.list_teams(
                user_id=user_id,
                page=1,
                per_page=100,  # Get all teams
                teams_filter='own-teams'
            )
            own_teams = own_teams_result.get('teams', [])

            # Get enrolled-teams (teams where user is member but not owner)
            enrolled_teams_result = team_service.list_teams(
                user_id=user_id,
                page=1,
                per_page=100,  # Get all teams
                teams_filter='enrolled-teams'
            )
            enrolled_teams = enrolled_teams_result.get('teams', [])

            # Combine both lists (avoid duplicates by team id)
            teams_dict = {}
            for team in own_teams + enrolled_teams:
                team_id = team.get('id')
                if team_id and team_id not in teams_dict:
                    teams_dict[team_id] = team
            
            teams_data = list(teams_dict.values())
            
            return teams_data
            
        except Exception as e:
            # Log error but return empty list to avoid breaking login/registration
            self.logger.error(f"Error fetching teams for user {user_id}: {str(e)}")
            return []


# Global instance
user_service = UserService()

