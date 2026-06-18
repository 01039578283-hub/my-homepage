Add-Type -AssemblyName System.Web
$inputDir = Join-Path (Get-Location) 'tmp\article_txt_input\A열_텍스트파일'
$outputDir = Join-Path (Get-Location) 'tmp\article_txt_generated'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
Get-ChildItem -Path $outputDir -Filter '*.txt' -File -ErrorAction SilentlyContinue | Remove-Item -Force

function HtmlEncode([string]$s) {
  if ($null -eq $s) { return '' }
  return [System.Web.HttpUtility]::HtmlEncode($s.Trim())
}

function StripTags([string]$s) {
  if ($null -eq $s) { return '' }
  $x = [regex]::Replace($s, '<br\s*/?>', "`n", 'IgnoreCase')
  $x = [regex]::Replace($x, '<[^>]+>', ' ')
  $x = [System.Web.HttpUtility]::HtmlDecode($x)
  $x = [regex]::Replace($x, '\s+', ' ').Trim()
  return $x
}

function CleanText([string]$s) {
  if ($null -eq $s) { return '' }
  $x = [System.Web.HttpUtility]::HtmlDecode($s)
  $x = $x -replace "`r", "`n"
  $x = [regex]::Replace($x, "[ \t]+`n", "`n")
  $x = [regex]::Replace($x, "`n{3,}", "`n`n")
  return $x.Trim()
}

function Get-HtmlBetween([string]$html, [string]$startPattern, [string]$endPattern) {
  $m = [regex]::Match($html, $startPattern + '(.*?)' + $endPattern, 'Singleline,IgnoreCase')
  if ($m.Success) { return $m.Groups[1].Value }
  return ''
}

function Extract-FirstParagraph([string]$html) {
  $m = [regex]::Match($html, '<p[^>]*>(.*?)</p>', 'Singleline,IgnoreCase')
  if ($m.Success) { return StripTags $m.Groups[1].Value }
  return ''
}

function Extract-HtmlTitle([string]$html) {
  $m = [regex]::Match($html, '<h1[^>]*>(.*?)</h1>|<h2[^>]*>(.*?)</h2>', 'Singleline,IgnoreCase')
  if ($m.Success) {
    if ($m.Groups[1].Value) { return StripTags $m.Groups[1].Value }
    return StripTags $m.Groups[2].Value
  }
  return ''
}

function Extract-SectionAfterHeading([string]$html, [string]$headingKeyword) {
  $pattern = '<h3[^>]*>\s*[^<]*' + [regex]::Escape($headingKeyword) + '[^<]*</h3>(.*?)(?=<h3|$)'
  $m = [regex]::Match($html, $pattern, 'Singleline,IgnoreCase')
  if ($m.Success) { return $m.Groups[1].Value }
  return ''
}

function Extract-TopLi([string]$html) {
  $items = New-Object System.Collections.Generic.List[string]
  $depth = 0
  $buf = New-Object System.Text.StringBuilder
  $inLi = $false
  foreach ($m in [regex]::Matches($html, '<(/?)(ul|li)[^>]*>|([^<]+)', 'IgnoreCase')) {
    if ($m.Groups[2].Value -eq 'ul') {
      if ($m.Groups[1].Value -eq '/') { $depth-- } else { $depth++ }
    } elseif ($m.Groups[2].Value -eq 'li') {
      if ($m.Groups[1].Value -eq '/') {
        if ($inLi -and $depth -eq 1) {
          $items.Add((StripTags $buf.ToString()))
          [void]$buf.Clear()
          $inLi = $false
        }
      } else {
        if ($depth -eq 1) { $inLi = $true; [void]$buf.Clear() }
      }
    } elseif ($inLi -and $depth -eq 1) {
      [void]$buf.Append($m.Groups[3].Value)
    }
  }
  return $items
}

function Extract-FaqHtml([string]$html) {
  $faqs = New-Object System.Collections.Generic.List[object]
  $section = Extract-SectionAfterHeading $html '자주 묻는 질문'
  foreach ($m in [regex]::Matches($section, '<h4[^>]*>(.*?)</h4>\s*<p[^>]*>(.*?)</p>', 'Singleline,IgnoreCase')) {
    $q = StripTags $m.Groups[1].Value
    $a = StripTags $m.Groups[2].Value
    if ($q -and $a) { $faqs.Add([pscustomobject]@{Q=$q;A=$a}) }
  }
  return $faqs
}

function Split-PlainSections([string]$text) {
  $lines = @($text -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  $title = if ($lines.Count -gt 0) { $lines[0] } else { '와와학습코칭센터 영어수학 전문학원' }
  $introLines = New-Object System.Collections.Generic.List[string]
  $i = 1
  while ($i -lt $lines.Count -and $lines[$i] -notmatch '^1\)') { $introLines.Add($lines[$i]); $i++ }
  $sections = @{}
  $current = ''
  for (; $i -lt $lines.Count; $i++) {
    $line = $lines[$i]
    if ($line -match '^[1-4]\)') { $current = $line; $sections[$current] = New-Object System.Collections.Generic.List[string] }
    elseif ($current) { $sections[$current].Add($line) }
  }
  return [pscustomobject]@{Title=$title; Intro=($introLines -join ' '); Sections=$sections}
}

function Take-ReasonCardsFromPlain($lines) {
  $cards = New-Object System.Collections.Generic.List[object]
  for ($i=0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\d+\.\s*(.+)$') {
      $head = $Matches[1].Trim()
      $body = if ($i + 1 -lt $lines.Count) { $lines[$i+1].Trim() } else { '' }
      $cards.Add([pscustomobject]@{Head=$head;Body=$body})
      $i++
    }
  }
  return $cards
}

function Take-TargetCardsFromPlain($lines) {
  $cards = New-Object System.Collections.Generic.List[object]
  $current = $null
  foreach ($line in $lines) {
    if ($line -match '^(초등|중학생|고등)') {
      if ($current) { $cards.Add($current) }
      $current = [pscustomobject]@{Head=$line;Items=(New-Object System.Collections.Generic.List[string]);Arrow=''}
    } elseif ($line -match '^-\s*(.+)$' -and $current) {
      $current.Items.Add($Matches[1].Trim())
    } elseif ($line -match '^→\s*(.+)$' -and $current) {
      $current.Arrow = '→ ' + $Matches[1].Trim()
    }
  }
  if ($current) { $cards.Add($current) }
  return $cards
}

function TakeSubjectCardsFromPlain($lines) {
  $cards = New-Object System.Collections.Generic.List[object]
  $current = $null
  foreach ($line in $lines) {
    if ($line -match '^(영어|수학) 수업 선택 기준') {
      if ($current) { $cards.Add($current) }
      $current = [pscustomobject]@{Head=$line;Items=(New-Object System.Collections.Generic.List[string]);Arrow=''}
    } elseif ($line -match '^-\s*(.+)$' -and $current) {
      $current.Items.Add($Matches[1].Trim())
    } elseif ($line -match '^→\s*(.+)$' -and $current) {
      $current.Arrow = '→ ' + $Matches[1].Trim()
    }
  }
  if ($current) { $cards.Add($current) }
  return $cards
}

function TakeFaqFromPlain($lines) {
  $faqs = New-Object System.Collections.Generic.List[object]
  for ($i=0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^Q\d+\.\s*(.+)$') {
      $q = $lines[$i]
      $a = ''
      if ($i + 1 -lt $lines.Count -and $lines[$i+1] -match '^A\.\s*(.+)$') { $a = $lines[$i+1] }
      $faqs.Add([pscustomobject]@{Q=$q;A=$a})
      $i++
    }
  }
  return $faqs
}

function Render-List($items) {
  $out = New-Object System.Text.StringBuilder
  [void]$out.AppendLine('          <ul>')
  foreach ($item in $items) { [void]$out.AppendLine('            <li>' + (HtmlEncode $item) + '</li>') }
  [void]$out.AppendLine('          </ul>')
  return $out.ToString().TrimEnd()
}

function Render-Article($title, $intro, $reasonCards, $targetCards, $subjectCards, $faqs, $closing) {
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.AppendLine('<main class="article-main">')
  [void]$sb.AppendLine('  <section class="article-hero">')
  [void]$sb.AppendLine('    <p class="article-eyebrow">LOCAL ACADEMY GUIDE</p>')
  [void]$sb.AppendLine('    <h1>' + (HtmlEncode $title) + '</h1>')
  [void]$sb.AppendLine('  </section>')
  if ($intro) { [void]$sb.AppendLine('  <p class="article-intro">' + (HtmlEncode $intro) + '</p>') }
  if ($reasonCards.Count -gt 0) {
    [void]$sb.AppendLine('  <section class="article-section">')
    [void]$sb.AppendLine('    <h2>우리 학원을 선택해야 하는 이유</h2>')
    [void]$sb.AppendLine('    <div class="article-card-grid">')
    foreach ($c in $reasonCards) {
      [void]$sb.AppendLine('      <article class="article-card">')
      [void]$sb.AppendLine('        <strong>' + (HtmlEncode $c.Head) + '</strong>')
      if ($c.Body) { [void]$sb.AppendLine('        <p>' + (HtmlEncode $c.Body) + '</p>') }
      [void]$sb.AppendLine('      </article>')
    }
    [void]$sb.AppendLine('    </div>')
    [void]$sb.AppendLine('  </section>')
  }
  if ($targetCards.Count -gt 0) {
    [void]$sb.AppendLine('  <section class="article-section">')
    [void]$sb.AppendLine('    <h2>수업 대상 학생 &amp; 학년별 학습 고민</h2>')
    [void]$sb.AppendLine('    <div class="article-target-list">')
    foreach ($c in $targetCards) {
      [void]$sb.AppendLine('      <article class="article-target-card">')
      [void]$sb.AppendLine('        <h3>' + (HtmlEncode $c.Head) + '</h3>')
      if ($c.Items.Count -gt 0) { [void]$sb.AppendLine((Render-List $c.Items)) }
      if ($c.Arrow) { [void]$sb.AppendLine('        <p class="article-arrow">' + (HtmlEncode $c.Arrow) + '</p>') }
      [void]$sb.AppendLine('      </article>')
    }
    [void]$sb.AppendLine('    </div>')
    [void]$sb.AppendLine('  </section>')
  }
  if ($subjectCards.Count -gt 0) {
    [void]$sb.AppendLine('  <section class="article-section">')
    [void]$sb.AppendLine('    <h2>과목별 선택 기준</h2>')
    [void]$sb.AppendLine('    <div class="article-subject-grid">')
    foreach ($c in $subjectCards) {
      [void]$sb.AppendLine('      <article class="article-subject-card">')
      [void]$sb.AppendLine('        <h3>' + (HtmlEncode $c.Head) + '</h3>')
      if ($c.Items.Count -gt 0) { [void]$sb.AppendLine((Render-List $c.Items)) }
      if ($c.Arrow) { [void]$sb.AppendLine('        <p class="article-arrow">' + (HtmlEncode $c.Arrow) + '</p>') }
      [void]$sb.AppendLine('      </article>')
    }
    [void]$sb.AppendLine('    </div>')
    [void]$sb.AppendLine('  </section>')
  }
  if ($faqs.Count -gt 0) {
    [void]$sb.AppendLine('  <section class="article-section">')
    [void]$sb.AppendLine('    <h2>자주 묻는 질문(FAQ)</h2>')
    [void]$sb.AppendLine('    <div class="article-faq-list">')
    $first = $true
    foreach ($f in $faqs) {
      $open = if ($first) { ' open' } else { '' }
      [void]$sb.AppendLine('      <details class="article-faq"' + $open + '>')
      [void]$sb.AppendLine('        <summary>' + (HtmlEncode $f.Q) + '</summary>')
      if ($f.A) { [void]$sb.AppendLine('        <p>' + (HtmlEncode $f.A) + '</p>') }
      [void]$sb.AppendLine('      </details>')
      $first = $false
    }
    [void]$sb.AppendLine('    </div>')
    [void]$sb.AppendLine('  </section>')
  }
  if ($closing) {
    [void]$sb.AppendLine('  <section class="article-closing">')
    [void]$sb.AppendLine('    <p>' + (HtmlEncode $closing) + '</p>')
    [void]$sb.AppendLine('  </section>')
  }
  [void]$sb.AppendLine('</main>')
  return $sb.ToString()
}

function Convert-HtmlOriginal([string]$html) {
  $title = Extract-HtmlTitle $html
  $intro = Extract-FirstParagraph $html
  $reasonSec = Extract-SectionAfterHeading $html '우리 학원'
  $reasonCards = New-Object System.Collections.Generic.List[object]
  foreach ($m in [regex]::Matches($reasonSec, '<li>\s*<strong>(.*?)</strong>\s*:?\s*(.*?)</li>', 'Singleline,IgnoreCase')) {
    $head = StripTags $m.Groups[1].Value
    $body = StripTags $m.Groups[2].Value
    if ($head) { $reasonCards.Add([pscustomobject]@{Head=$head;Body=$body}) }
  }
  $targetSec = Extract-SectionAfterHeading $html '수업 대상'
  $targetCards = New-Object System.Collections.Generic.List[object]
  foreach ($m in [regex]::Matches($targetSec, '<strong>(.*?)</strong>\s*<ul>(.*?)</ul>', 'Singleline,IgnoreCase')) {
    $head = StripTags $m.Groups[1].Value
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($im in [regex]::Matches($m.Groups[2].Value, '<li>(.*?)</li>', 'Singleline,IgnoreCase')) { $items.Add((StripTags $im.Groups[1].Value)) }
    if ($head) { $targetCards.Add([pscustomobject]@{Head=$head;Items=$items;Arrow=''}) }
  }
  $subjectSec = Extract-SectionAfterHeading $html '과목별'
  $subjectCards = New-Object System.Collections.Generic.List[object]
  foreach ($m in [regex]::Matches($subjectSec, '<strong>(.*?)</strong>\s*<ul>(.*?)</ul>', 'Singleline,IgnoreCase')) {
    $head = StripTags $m.Groups[1].Value
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($im in [regex]::Matches($m.Groups[2].Value, '<li>(.*?)</li>', 'Singleline,IgnoreCase')) { $items.Add((StripTags $im.Groups[1].Value)) }
    if ($head -and $items.Count -gt 0) { $subjectCards.Add([pscustomobject]@{Head=$head;Items=$items;Arrow=''}) }
  }
  $faqs = Extract-FaqHtml $html
  $paras = @([regex]::Matches($html, '<p[^>]*>(.*?)</p>', 'Singleline,IgnoreCase') | ForEach-Object { StripTags $_.Groups[1].Value } | Where-Object { $_ })
  $closing = if ($paras.Count -gt 1) { $paras[-1] } else { '' }
  return Render-Article $title $intro $reasonCards $targetCards $subjectCards $faqs $closing
}

function Convert-PlainOriginal([string]$text) {
  $data = Split-PlainSections $text
  $sections = $data.Sections
  $reasonLines = @(); $targetLines = @(); $subjectLines = @(); $faqLines = @()
  foreach ($key in $sections.Keys) {
    if ($key -match '수업 대상') { $targetLines = @($sections[$key]) }
    elseif ($key -match '과목별') { $subjectLines = @($sections[$key]) }
    elseif ($key -match '우리 학원|선택해야') { $reasonLines = @($sections[$key]) }
    elseif ($key -match 'FAQ|자주') { $faqLines = @($sections[$key]) }
  }
  $reasonCards = Take-ReasonCardsFromPlain $reasonLines
  $targetCards = Take-TargetCardsFromPlain $targetLines
  $subjectCards = TakeSubjectCardsFromPlain $subjectLines
  $faqs = TakeFaqFromPlain $faqLines
  $closing = ''
  $allLines = @($text -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  if ($allLines.Count -gt 0) { $closing = $allLines[-1] }
  return Render-Article $data.Title $data.Intro $reasonCards $targetCards $subjectCards $faqs $closing
}

$files = Get-ChildItem -Path $inputDir -File -Filter '*.txt' | Sort-Object { [int]([regex]::Match($_.BaseName, '\d+').Value) }
$idx = 1
foreach ($file in $files) {
  $raw = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::Default)
  $raw = CleanText $raw
  if ($raw -match '<h\d|<p|<ul|<li') { $html = Convert-HtmlOriginal $raw } else { $html = Convert-PlainOriginal $raw }
  $outName = ('{0:D4}.txt' -f $idx)
  [System.IO.File]::WriteAllText((Join-Path $outputDir $outName), $html, [System.Text.Encoding]::UTF8)
  $idx++
}

$outZip = Join-Path (Get-Location) 'article_html_txt_0001-0371_generated.zip'
if (Test-Path $outZip) { Remove-Item -LiteralPath $outZip -Force }
Compress-Archive -Path (Join-Path $outputDir '*.txt') -DestinationPath $outZip -Force
[pscustomobject]@{ InputCount=$files.Count; OutputCount=(Get-ChildItem -Path $outputDir -Filter '*.txt').Count; Zip=$outZip }
