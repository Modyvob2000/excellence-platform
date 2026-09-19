package com.excellence.platform.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.NavType
import com.excellence.platform.ui.screens.admin.AdminScreen
import com.excellence.platform.ui.screens.admin.ReviewScreen
import com.excellence.platform.ui.screens.auth.LoginScreen
import com.excellence.platform.ui.screens.content.GradesScreen
import com.excellence.platform.ui.screens.content.LessonsScreen
import com.excellence.platform.ui.screens.content.SubjectsScreen
import com.excellence.platform.ui.screens.content.UnitsScreen
import com.excellence.platform.ui.screens.exams.AttemptScreen
import com.excellence.platform.ui.screens.home.HomeScreen
import com.excellence.platform.ui.screens.importcenter.ImportCenterScreen
import com.excellence.platform.ui.screens.importcenter.ImportHistoryScreen
import com.excellence.platform.ui.screens.questions.QuestionsScreen
import com.excellence.platform.ui.screens.results.HistoryScreen
import com.excellence.platform.ui.screens.results.ResultScreen

object Routes {
    const val LOGIN = "login"
    const val HOME = "home"
    const val GRADES = "grades"
    const val SUBJECTS = "subjects/{gradeId}"
    const val UNITS = "units/{subjectId}"
    const val LESSONS = "lessons/{unitId}"
    const val QUESTIONS = "questions/{lessonId}"
    const val ATTEMPT = "attempt/{examId}"
    const val RESULT = "result/{attemptId}"
    const val HISTORY = "history"
    const val IMPORT_CENTER = "import_center"
    const val IMPORT_HISTORY = "import_history"
    const val REVIEW = "review"
    const val ADMIN = "admin"

    fun subjects(gradeId: Int) = "subjects/$gradeId"
    fun units(subjectId: Int) = "units/$subjectId"
    fun lessons(unitId: Int) = "lessons/$unitId"
    fun questions(lessonId: Int) = "questions/$lessonId"
    fun attempt(examId: Int) = "attempt/$examId"
    fun result(attemptId: Int) = "result/$attemptId"
}

@Composable
fun ExcellenceNavHost(navController: NavHostController = rememberNavController()) {
    NavHost(navController = navController, startDestination = Routes.LOGIN) {
        composable(Routes.LOGIN) { LoginScreen(onLoggedIn = { navController.navigate(Routes.HOME) }) }

        composable(Routes.HOME) { HomeScreen(navController = navController) }

        composable(Routes.GRADES) { GradesScreen(navController = navController) }

        composable(Routes.SUBJECTS, arguments = listOf(navArgument("gradeId") { type = NavType.IntType })) {
            SubjectsScreen(navController = navController,
                            gradeId = it.arguments!!.getInt("gradeId"))
        }
        composable(Routes.UNITS, arguments = listOf(navArgument("subjectId") { type = NavType.IntType })) {
            UnitsScreen(navController = navController,
                        subjectId = it.arguments!!.getInt("subjectId"))
        }
        composable(Routes.LESSONS, arguments = listOf(navArgument("unitId") { type = NavType.IntType })) {
            LessonsScreen(navController = navController,
                          unitId = it.arguments!!.getInt("unitId"))
        }
        composable(Routes.QUESTIONS, arguments = listOf(navArgument("lessonId") { type = NavType.IntType })) {
            QuestionsScreen(lessonId = it.arguments!!.getInt("lessonId"))
        }
        composable(Routes.ATTEMPT, arguments = listOf(navArgument("examId") { type = NavType.IntType })) {
            AttemptScreen(navController = navController, examId = it.arguments!!.getInt("examId"))
        }
        composable(Routes.RESULT, arguments = listOf(navArgument("attemptId") { type = NavType.IntType })) {
            ResultScreen(attemptId = it.arguments!!.getInt("attemptId"))
        }
        composable(Routes.HISTORY) { HistoryScreen() }
        composable(Routes.IMPORT_CENTER) { ImportCenterScreen() }
        composable(Routes.IMPORT_HISTORY) { ImportHistoryScreen() }
        composable(Routes.REVIEW) { ReviewScreen() }
        composable(Routes.ADMIN) { AdminScreen(navController = navController) }
    }
}
