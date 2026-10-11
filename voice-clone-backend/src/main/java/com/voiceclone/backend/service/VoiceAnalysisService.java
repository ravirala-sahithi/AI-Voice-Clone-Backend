
package com.voiceclone.backend.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.io.IOException;
import java.util.Map;

@Service
public class VoiceAnalysisService {

    @Value("${ai.service.url:http://127.0.0.1:8000}")
    private String aiServiceUrl;

    private final RestTemplate restTemplate = new RestTemplate();

    public Map<String, Object> analyzeAudio(MultipartFile file) {

        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Please upload an audio file."
            );
        }

        if (file.getSize() > 20L * 1024 * 1024) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Maximum audio file size is 20 MB."
            );
        }

        try {
            String filename = file.getOriginalFilename();

            if (filename == null || filename.isBlank()) {
                filename = "audio.wav";
            }

            final String uploadedFilename = filename;

            ByteArrayResource resource =
                    new ByteArrayResource(file.getBytes()) {
                        @Override
                        public String getFilename() {
                            return uploadedFilename;
                        }
                    };

            HttpHeaders fileHeaders = new HttpHeaders();
            fileHeaders.setContentType(
                    MediaType.APPLICATION_OCTET_STREAM
            );

            HttpEntity<ByteArrayResource> filePart =
                    new HttpEntity<>(resource, fileHeaders);

            MultiValueMap<String, Object> requestBody =
                    new LinkedMultiValueMap<>();

            requestBody.add("file", filePart);

            HttpHeaders requestHeaders = new HttpHeaders();
            requestHeaders.setContentType(
                    MediaType.MULTIPART_FORM_DATA
            );

            HttpEntity<MultiValueMap<String, Object>> request =
                    new HttpEntity<>(requestBody, requestHeaders);

            return restTemplate.postForObject(
                    aiServiceUrl + "/detect",
                    request,
                    Map.class
            );

        } catch (IOException e) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Could not read the uploaded audio file."
            );
        } catch (RestClientException e) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "AI service is unavailable. Please check that it is running."
            );
        }
    }
}
