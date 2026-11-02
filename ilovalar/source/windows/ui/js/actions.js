// Bir nechta sahifada işlatiladigan amallar.
import { openWeb } from './api.js';
import { lessonHistory } from './store.js';

/** Darsni alohida oynada oçadi va "yaqinda oçilgan" tarixiga yozadi. */
export function openLesson(lesson, course) {
  lessonHistory.track(lesson, course);
  return openWeb(`/lessons/${Number(lesson.id)}/`);
}
