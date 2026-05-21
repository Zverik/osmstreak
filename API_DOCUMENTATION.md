# OSM Streak API Documentation

This documentation describes how to retrieve your OSM Streak profile data and integrate it into your OpenStreetMap profile.

## API Endpoints

### 1. JSON API - Get user data in JSON

**Endpoint:** `GET /api/user/<username>`

**Description:** Returns the user's public data in JSON format (score, level, streak).

**Parameters:**
- `<username>` - The OSM username (case-sensitive)

**Example request:**
```
GET /api/user/MapperName
```

**Response (200 OK):**
```json
{
  "name": "MapperName",
  "score": 1250,
  "level": 3,
  "streak": 45,
  "uid": 123456
}
```

**Errors:**
- `404 Not Found` - User doesn't exist

**Use cases:**
- Integrate data into custom applications
- Create personal dashboards
- Sync data with other systems

---

### 2. HTML Widget - Embed in OSM profile

**Endpoint:** `GET /widget/<username>`

**Description:** Returns an embeddable HTML widget showing the user's score, level, and streak with an elegant style.

**Parameters:**
- `<username>` - The OSM username (case-sensitive)

**How to use:**

In your OpenStreetMap profile, add an iframe in the "About" or "Description" section:

```html
<iframe src="https://streak.osmz.ru/widget/MapperName" 
        width="340" 
        height="200" 
        style="border:none; border-radius: 8px;">
</iframe>
```

**Features:**
- ✅ Responsive and mobile-friendly
- ✅ Shows Score, Level, Streak Days
- ✅ Link to official OSM Streak website
- ✅ Auto-updates from the database

**Errors:**
- `404 Not Found` - User does not exist

---

### 3. SVG Badge - Use in README/Profiles

**Endpoint:** `GET /badge/<username>`

**Description:** Returns a dynamic SVG badge with the user's data. Perfect for GitHub READMEs, profiles, etc.

**Parameters:**
- `<username>` - The OSM username (case-sensitive)

**How to use:**

**In Markdown (GitHub README, etc.):**
```markdown
![OSM Streak Badge](https://streak.osmz.ru/badge/MapperName)
```

**In HTML:**
```html
<img src="https://streak.osmz.ru/badge/MapperName" alt="OSM Streak Badge" />
```

**In OpenStreetMap profile:**
```html
<img src="https://streak.osmz.ru/badge/MapperName" alt="OSM Streak" style="max-width: 350px;" />
```

**Caratteristiche:**
- ✅ Dynamic SVG (real-time updates)
- ✅ Shows username, score, level, and streak
- ✅ Works anywhere images are supported

**Errors:**
- `404 Not Found` - User does not exist

---

## Usage Examples

### Example 1: Add the widget to your OSM profile

1. Go to [openstreetmap.org](https://www.openstreetmap.org)
2. Log in to your profile
3. Click "Edit Profile"
4. Nn the "About me" section, add:
```html
<h3>🎯 My OSM Streak Stats</h3>
<iframe src="https://streak.osmz.ru/widget/TuoNomeUtente" 
        width="340" 
        height="200" 
        style="border:none; border-radius: 8px;">
</iframe>
```
5. Save your changes

### Example 2: Add the badge to GitHub

In your GitHub README.md:
```markdown
# My OSM Contributions

![OSM Streak](https://streak.osmz.ru/badge/TuoNomeUtente)

I'm mapping every day with OSM Streak!
```

### Example 3: Use the JSON API in JavaScript

```javascript
async function getStreakData(username) {
  try {
    const response = await fetch(`https://streak.osmz.ru/api/user/${username}`);
    
    if (!response.ok) {
      throw new Error('User not found');
    }
    
    const data = await response.json();
    
    console.log(`${data.name} - Level ${data.level}, Score: ${data.score}`);
    console.log(`🔥 Streak: ${data.streak} days`);
    
    return data;
  } catch (error) {
    console.error('Error fetching streak data:', error);
  }
}

// Uso
getStreakData('MapperName');
```

---

## Important Notes

### Case Sensitivity
- Usernames are **case-sensitive**
- `mapper` e `Mapper` are different users
- Check the capitalization of your OSM name

### Privacy
- All endpoints are **public**
- No authentication required
- The data shown is the same as what's visible in the public profile

### Rate Limiting
- No official rate limit at this time
- For heavy usage, contact the administrators

### CORS
- Endpoints support CORS for browser requests

---

## Troubleshooting

**D: I'm getting 404 Not Found**
- Check that the username is correct and has the right capitalization
- Verify that the user has completed at least one challenge in OSM Streak

**D: The widget doesn't load**
- Check that the URL is correct
- Verify that the domain is accessible
- Check the browser console for errors

**D: The SVG badge doesn't update**
- The badge is dynamic and updates when you visit the URL
- Browsers and services may cache the image
- If using CDN services, they may cache it for longer

---
