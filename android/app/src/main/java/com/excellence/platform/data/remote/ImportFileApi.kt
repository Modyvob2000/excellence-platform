package com.excellence.platform.data.remote

import kotlinx.serialization.Serializable
import okhttp3.MultipartBody
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Query

interface ImportFileApi {
    /** يطابق POST /import/file?file_type=... في الـbackend (routers/import_.py). */
    @Multipart
    @POST("import/file")
    suspend fun uploadFile(
        @Query("file_type") fileType: String,  // PDF | WORD | EXCEL
        @Part file: MultipartBody.Part,
    ): BatchOut

    @Multipart
    @POST("import/csv")
    suspend fun uploadCsv(@Part file: MultipartBody.Part): BatchOut
}
