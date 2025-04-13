from typing import Optional

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.progress import TaskID


class MultiTaskProgress:
    def __init__(self):
        
        self.overall_progress = Progress(
            "{task.description}",
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
        )
        self.overall_task = self.overall_progress.add_task("All Jobs", total=0)

        self.job_progress = Progress(
            "{task.description}",
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
        )

        self.tasks : list[TaskID] = []

    def add_task(self, description: str, total: Optional[int] = None) -> TaskID:
        task = self.job_progress.add_task(description, total=total)
        self.refresh_overall_progress_bar()
        self.tasks.append(task)
        return task
    
    def complete_task(self, task_id: TaskID):
        self.job_progress.tasks[task_id].total = self.job_progress.tasks[task_id].completed
        self.refresh_overall_progress_bar()

    def advance_task(self, task_id: TaskID, advance: int = 1):
        self.job_progress.advance(task_id, advance)
        self.refresh_overall_progress_bar()

    def set_description(self, task_id: TaskID, description: str):
        self.job_progress.tasks[task_id].description = description
        self.refresh_overall_progress_bar()

    def refresh_overall_progress_bar(self):
        if not self.job_progress.tasks:
            self.overall_progress.update(self.overall_task, completed=0, total=0)
            return

        total = sum(
            (
                task.total
                if task.total is not None
                else 1 # Assuming 1 for tasks without a total
            )
            for task in self.job_progress.tasks
        )
        completed = sum(task.completed for task in self.job_progress.tasks)
        self.overall_progress.update(self.overall_task, completed=completed, total=total)

    def render(self) -> Table.grid:
        progress_table = Table.grid()
        progress_table.add_row(
            Panel.fit(
                self.overall_progress, title="Overall Progress", border_style="green"
            )
        )
        progress_table.add_row(
            Panel.fit(self.job_progress, title="[b]Jobs", border_style="red"),
        )
        return progress_table