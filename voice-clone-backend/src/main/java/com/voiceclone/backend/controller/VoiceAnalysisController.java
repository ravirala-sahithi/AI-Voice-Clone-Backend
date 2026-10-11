
package com.voiceclone.backend.controller;

import com.voiceclone.backend.service.VoiceAnalysisService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

@RestController
@RequestMapping("/api/voice")
public class VoiceAnalysisController {

    private final VoiceAnalysisService voiceAnalysisService;

    public VoiceAnalysisController(
            VoiceAnalysisService voiceAnalysisService) {
        this.voiceAnalysisService = voiceAnalysisService;
    }

    @PostMapping(
            value = "/analyze",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> analyzeAudio(
            @RequestParam("file") MultipartFile file) {

        Map<String, Object> result =
                voiceAnalysisService.analyzeAudio(file);

        return ResponseEntity.ok(result);
    }
}
