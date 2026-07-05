function updateTaskState(taskId, newState) {
  const taskElement = document.getElementById(`task-${taskId}`);
  if (taskElement) {
    taskElement.classList.add('task-state-flash');
    setTimeout(() => taskElement.classList.remove('task-state-flash'), 500);
  }
}